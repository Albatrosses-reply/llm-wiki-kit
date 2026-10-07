"""초록 보충. Crossref·OpenAlex에 초록이 없는 논문을 아래 순서로 채운다. 키가 없는 단계는 건너뛴다.

1. Elsevier (DOI 10.1016/…): ScienceDirect Article API, 비밀값 ELSEVIER_API_KEY
   Elsevier는 Crossref에 초록을 등록하지 않는다(JUE·RSUE·JHE·Land Use Policy·Cities 등).
2. Semantic Scholar: 나머지 전부(Taylor & Francis, 시카고대 출판사 등). 비밀값 S2_API_KEY(없어도 되지만 자주 막힌다)

출판사 웹페이지는 긁지 않는다(봇 차단, 이용약관).
"""
from __future__ import annotations

import logging
import os
import urllib.parse

from .util import Http, clean_abstract

log = logging.getLogger("alert")

ELSEVIER = "https://api.elsevier.com/content/article/doi/"
S2_BATCH = "https://api.semanticscholar.org/graph/v1/paper/batch"


def elsevier(papers: list, http: Http, key: str) -> int:
    n = 0
    for p in papers:
        if p.abstract or not p.doi.startswith("10.1016/"):
            continue
        d = http.get_json(ELSEVIER + urllib.parse.quote(p.doi, safe="/()._-;:"), {"view": "META_ABS"},
                          headers={"X-ELS-APIKey": key})
        core = ((d or {}).get("full-text-retrieval-response") or {}).get("coredata") or {}
        ab = clean_abstract(core.get("dc:description"))
        if ab:
            p.abstract, p.abstract_src = ab, "Elsevier"
            n += 1
    return n


def semantic_scholar(papers: list, http: Http, key: str = "") -> int:
    todo = [p for p in papers if not p.abstract]
    n = 0
    for i in range(0, len(todo), 400):  # 한 번에 최대 500개
        chunk = todo[i:i + 400]
        res = http.request(S2_BATCH, {"fields": "abstract"}, body={"ids": [f"DOI:{p.doi}" for p in chunk]},
                           headers={"x-api-key": key} if key else None)
        for p, r in zip(chunk, res or []):
            ab = clean_abstract((r or {}).get("abstract"))
            if ab:
                p.abstract, p.abstract_src = ab, "Semantic Scholar"
                n += 1
    return n


def fill(papers: list, http: Http | None = None) -> dict:
    http = http or Http(delay=0.2)
    ek = os.environ.get("ELSEVIER_API_KEY", "").strip()
    sk = os.environ.get("S2_API_KEY", "").strip()
    stats = {"before": sum(1 for p in papers if not p.abstract)}
    stats["elsevier"] = elsevier(papers, http, ek) if ek else 0
    stats["s2"] = semantic_scholar(papers, Http(delay=1.1), sk)  # 소개 등급 한도 초당 1회
    stats["after"] = sum(1 for p in papers if not p.abstract)
    log.info(f"초록 보충: 없음 {stats['before']} → Elsevier {stats['elsevier']} · Semantic Scholar {stats['s2']} → 남음 {stats['after']}")
    return stats
