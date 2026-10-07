"""추가 저널 찾기: 영문 이름이나 ISSN → {abbrev, name, issn} (Crossref 저널 API)."""
from __future__ import annotations

import re

from .util import Http

CROSSREF_J = "https://api.crossref.org/journals"
ISSN_RE = re.compile(r"^\d{4}-?\d{3}[\dXx]$")


def abbrev_of(title: str) -> str:
    words = [w for w in re.findall(r"[A-Za-z]+", title) if w.lower() not in ("of", "and", "the", "for", "in", "on")]
    return "".join(w[0].upper() for w in words)[:8] or "J"


def resolve(query: str, http: Http | None = None) -> dict | None:
    http = http or Http(delay=0.3)
    q = query.strip()
    if ISSN_RE.match(q):
        issn = (q if "-" in q else f"{q[:4]}-{q[4:]}").upper()
        d = http.get_json(f"{CROSSREF_J}/{issn}")
        items = [d["message"]] if d and d.get("message") else []
    else:
        d = http.get_json(CROSSREF_J, {"query": q, "rows": 10})
        items = ((d or {}).get("message") or {}).get("items") or []
        norm = lambda s: re.sub(r"[^a-z0-9]", "", s.lower().replace("&", "and"))  # noqa: E731
        items.sort(key=lambda it: norm(it.get("title", "")) != norm(q))
    for it in items:
        if it.get("ISSN"):
            return {"abbrev": abbrev_of(it["title"]), "name": it["title"], "issn": it["ISSN"][:2]}
    return None
