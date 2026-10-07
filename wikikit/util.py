"""공용 유틸: JSON HTTP 요청(재시도), 텍스트 정리."""
from __future__ import annotations

import html
import json
import logging
import re
import socket
import time
import urllib.error
import urllib.parse
import urllib.request

log = logging.getLogger("alert")

TAG_RE = re.compile(r"<[^>]+>")
WS_RE = re.compile(r"\s+")
RETRY_CODES = {429, 500, 502, 503, 504}
QUOTA_WAIT = 300  # Retry-After가 이보다 길면 일일 할당량 소진으로 보고 그 호스트를 이번 실행에서 끈다


def clean_text(s) -> str:
    if not s:
        return ""
    s = TAG_RE.sub(" ", str(s))
    return WS_RE.sub(" ", html.unescape(s)).strip()


def clean_title(s) -> str:
    return re.sub(r"\s*\*+\s*$", "", clean_text(s)).strip()


def clean_abstract(s) -> str:
    s = clean_text(s)
    return re.sub(r"^(abstract|summary)\s*[:.\-–—]?\s+", "", s, flags=re.I).strip()


def norm_doi(doi) -> str:
    d = (doi or "").strip().lower()
    d = re.sub(r"^https?://(dx\.)?doi\.org/", "", d)
    return d.removeprefix("doi:").strip()


class Http:
    """urllib 기반 JSON 요청. 429/5xx는 기다렸다가 재시도한다."""

    def __init__(self, mailto: str = "", timeout: float = 40, delay: float = 0.25, tries: int = 4):
        self.timeout, self.delay, self.tries = timeout, delay, tries
        self.down: dict[str, float] = {}
        contact = f" (mailto:{mailto})" if mailto else ""
        self.headers = {"User-Agent": f"journal-alert/1.0{contact}", "Accept": "application/json"}

    def request(self, url: str, params: dict | None = None, body: dict | None = None, headers: dict | None = None):
        full = url + (f"?{urllib.parse.urlencode(params, safe=':,|*')}" if params else "")
        host = urllib.parse.urlsplit(url).netloc
        if self.down.get(host, 0) > time.time():
            return None
        hdr = {**self.headers, **(headers or {})}
        data = None
        if body is not None:
            data = json.dumps(body).encode("utf-8")
            hdr["Content-Type"] = "application/json"
        for attempt in range(1, self.tries + 1):
            try:
                req = urllib.request.Request(full, data=data, headers=hdr, method="POST" if data else "GET")
                with urllib.request.urlopen(req, timeout=self.timeout) as r:
                    out = json.loads(r.read().decode("utf-8"))
                if self.delay:
                    time.sleep(self.delay)
                return out
            except urllib.error.HTTPError as e:
                if e.code == 404:
                    return None
                wait = _retry_after(e)
                if e.code == 429 and wait > QUOTA_WAIT:
                    self.down[host] = time.time() + wait
                    log.warning(f"{host} 할당량 소진, 이번 실행에서는 건너뜀")
                    return None
                if e.code in RETRY_CODES and attempt < self.tries:
                    time.sleep(min(wait or 5.0 * attempt, 60.0))
                    continue
                log.warning(f"{host} HTTP {e.code}")
                return None
            except (urllib.error.URLError, socket.timeout, TimeoutError, ConnectionError, json.JSONDecodeError) as e:
                if attempt < self.tries:
                    time.sleep(3.0 * attempt)
                    continue
                log.warning(f"{host} 요청 실패: {e}")
                return None
        return None

    def get_json(self, url: str, params: dict | None = None, headers: dict | None = None):
        return self.request(url, params, headers=headers)


def _retry_after(e) -> float:
    try:
        return float(e.headers.get("Retry-After", ""))
    except (TypeError, ValueError, AttributeError):
        return 0.0
