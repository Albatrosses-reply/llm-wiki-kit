"""위키 후보 고르기: ① 메일의 📥 버튼 회신(Gmail IMAP) ② Obsidian inbox/alerts 체크박스 [x] → 후보 노트(inbox/starred).

자기 자신에게 보낸 메일은 Gmail이 '읽음'으로 둘 수 있어, 읽음 여부 대신 최근 7일·제목 키워드로 찾고 Message-ID로 중복을 막는다.
"""
from __future__ import annotations

import email
import imaplib
import logging
import re
from datetime import date, timedelta
from email.header import decode_header, make_header
from email.utils import parseaddr

from . import config as C
from . import vault as V
from .util import clean_text

log = logging.getLogger("wikikit")
CHECKED_LINE = re.compile(r"\[[xX]\][^\n]*?hash:\s*([0-9a-f]{12})", re.I)
HASH_ANY = re.compile(r"hash:\s*([0-9a-f]{12})", re.I)


def _dedupe(xs) -> list[str]:
    out = []
    for x in xs:
        if x.lower() not in out:
            out.append(x.lower())
    return out


def parse_star_message(subject: str, body: str, kw: str) -> list[str]:
    """단건: 제목 '<kw> <hash>'. 묶음: 제목 '<kw> BATCH' + 본문 '[x] hash:'. 그 밖에는 본문의 hash."""
    if re.search(re.escape(kw) + r"\s+BATCH", subject or "", re.I):
        return _dedupe(CHECKED_LINE.findall(body or ""))
    m = re.search(re.escape(kw) + r"\s+([0-9a-f]{12})\b", subject or "", re.I)
    if m:
        return [m.group(1).lower()]
    return _dedupe(HASH_ANY.findall(body or ""))


def _decode(v: str) -> str:
    try:
        return str(make_header(decode_header(v or "")))
    except Exception:  # noqa: BLE001
        return v or ""


def body_text(msg) -> str:
    plain = htm = None
    for part in (msg.walk() if msg.is_multipart() else [msg]):
        ctype = part.get_content_type()
        payload = part.get_payload(decode=True)
        if ctype not in ("text/plain", "text/html") or not isinstance(payload, (bytes, bytearray)):
            continue
        text = payload.decode(part.get_content_charset() or "utf-8", errors="ignore")
        if ctype == "text/plain" and plain is None:
            plain = text
        elif ctype == "text/html" and htm is None:
            htm = text
    if plain:
        return plain
    if htm:
        return "\n".join(clean_text(x) for x in re.sub(r"(?i)<br\s*/?>|</p>|</div>|</li>", "\n", htm).split("\n"))
    return ""


def imap_hashes(cfg: dict, store) -> list[str]:
    user, pw, kw = cfg.get("gmail", ""), C.secret("GMAIL_APP_PASSWORD"), cfg.get("star_keyword", "WIKI-STAR")
    if not (user and pw):
        return []
    allowed = {user.lower(), (cfg.get("recipient") or user).lower()}
    since = (date.today() - timedelta(days=7)).strftime("%d-%b-%Y")
    out: list[str] = []
    M = imaplib.IMAP4_SSL("imap.gmail.com", 993, timeout=60)
    try:
        M.login(user, pw)
        M.select("INBOX")
        typ, data = M.uid("SEARCH", None, f'(SINCE {since} SUBJECT "{kw}")')
        for uid in (data[0].split() if typ == "OK" and data and data[0] else []):
            typ, md = M.uid("FETCH", uid, "(BODY.PEEK[])")
            raw = next((p[1] for p in (md or []) if isinstance(p, tuple) and len(p) > 1), None)
            if typ != "OK" or not raw:
                continue
            msg = email.message_from_bytes(raw)
            mid = msg.get("Message-ID") or f"uid:{uid.decode()}"
            if parseaddr(msg.get("From", ""))[1].lower() not in allowed or store.mail_seen(mid):
                continue
            hs = parse_star_message(_decode(msg.get("Subject", "")), body_text(msg), kw)
            out += hs
            log.info(f"메일로 고름: {len(hs)}건")
    finally:
        try:
            M.logout()
        except Exception:  # noqa: BLE001
            pass
    return _dedupe(out)


def poll(cfg: dict, store) -> dict:
    vault = cfg["vault_path"]
    res = {"checked": 0, "mail": 0, "new": 0}
    hs = V.scan_checked(vault)
    res["checked"] = sum(1 for h in hs if store.star(h, "obsidian"))
    try:
        mh = imap_hashes(cfg, store)
        newly = [h for h in mh if store.star(h, "email")]
        res["mail"] = len(newly)
        if newly:
            V.mark_checked(vault, newly)
    except Exception as e:  # noqa: BLE001
        log.warning(f"메일 확인 실패: {e}")
    taken = store.citekeys() | {f.stem for f in (vault / "wiki" / "sources").glob("*.md")}
    for row in store.starred("note_path IS NULL"):
        ck = row["citekey"] or V.make_citekey([a for a in (row["authors"] or "").split(" | ") if a], (row["pub_date"] or "")[:4], taken)
        taken.add(ck)
        path = V.write_candidate(vault, row, ck)
        store.update(row["doi"], citekey=ck, note_path=str(path))
        res["new"] += 1
        log.info(f"후보 노트: {path.name}")
    return res
