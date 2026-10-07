"""Zotero(선택): 데스크톱 Zotero가 켜져 있으면 고른 논문을 커넥터로 저장한다. 꺼져 있으면 아무것도 하지 않고 다음에 다시 시도한다."""
from __future__ import annotations

import json
import logging
import urllib.request
import uuid

log = logging.getLogger("wikikit")
BASE = "http://127.0.0.1:23119/connector"


def ping() -> bool:
    try:
        with urllib.request.urlopen(f"{BASE}/ping", timeout=3) as r:
            return r.status == 200
    except Exception:  # noqa: BLE001
        return False


def item_of(row) -> dict:
    creators = []
    for a in (row["authors"] or "").split(" | "):
        if a:
            parts = a.rsplit(" ", 1)
            creators.append({"firstName": parts[0] if len(parts) == 2 else "", "lastName": parts[-1], "creatorType": "author"})
    return {"itemType": "journalArticle", "title": row["title"], "creators": creators, "date": row["pub_date"] or "",
            "publicationTitle": row["journal"] or "", "DOI": row["doi"], "url": f"https://doi.org/{row['doi']}",
            "abstractNote": row["abstract"] or "", "tags": [{"tag": "llm-wiki"}], "libraryCatalog": "LLM Wiki"}


def save(rows: list) -> int:
    if not rows or not ping():
        return 0
    body = json.dumps({"sessionID": uuid.uuid4().hex, "uri": "http://127.0.0.1/", "items": [item_of(r) for r in rows]}).encode("utf-8")
    req = urllib.request.Request(f"{BASE}/saveItems", data=body, method="POST",
                                 headers={"Content-Type": "application/json", "X-Zotero-Connector-API-Version": "3"})
    try:
        with urllib.request.urlopen(req, timeout=120) as r:
            ok = r.status in (200, 201)
    except Exception as e:  # noqa: BLE001
        log.warning(f"Zotero 저장 실패: {e}")
        return 0
    if ok:
        log.info(f"Zotero에 {len(rows)}편 저장")
    return len(rows) if ok else 0
