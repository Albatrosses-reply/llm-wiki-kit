"""저널 신간 수집: Crossref(DOI 등록일 기준) ∪ OpenAlex(출판일 기준), DOI로 병합.

Crossref는 DOI가 등록된 당일, OpenAlex는 보통 하루 이상 늦게 잡힌다. 초록은 둘 중 있는 쪽을 쓰고,
그래도 없으면 abstracts.fill이 출판사 API·Semantic Scholar로 보충한다.
"""
from __future__ import annotations

import os
import re
from dataclasses import dataclass, field
from datetime import date
from functools import lru_cache

from .util import Http, clean_abstract, clean_title, norm_doi

OPENALEX = "https://api.openalex.org/works"
CROSSREF = "https://api.crossref.org/works"
PAGE = 100
MAX_PAGES = 5

# 논문이 아닌 항목(표지, 정정문, 학회 공지 등). 원래 초록이 없어서 '초록 없음'으로 섞여 나오던 것들
EXCLUDE = [re.compile(p, re.I) for p in (
    r"^(front|back) ?matter", r"^issue information", r"^editorial board", r"^masthead", r"^table of contents",
    r"^(erratum|corrigendum|correction|retraction)\b\s*(to\b|notice\b|:|[-–—]|$)", r"[-–—:]\s*(erratum|corrigendum|correction|retraction)\s*$",
    r"^(correction|erratum) to\b", r"^forthcoming papers", r"^referees", r"^index to volume", r"^announcement",
    r"^in memoriam", r"^report of the", r"annual report", r"^editors?.? note", r"^cover\b", r"^list of",
    r"^preface", r"^acknowledg", r"^call for papers", r"^volume information", r"^contents$",
    r"^notes? to contributors", r"^editor.{0,3}s? comments", r"^from the editors?\b", r"^editorial$",
    r"election of fellows", r"^submission of manuscripts", r"^the econometric society\b", r"^book reviews?$",
)]
BAD_TYPES = {"paratext", "erratum", "editorial", "letter", "retraction", "peer-review", "supplementary-materials"}


@dataclass
class Paper:
    doi: str
    title: str
    authors: list = field(default_factory=list)
    journal: str = ""
    abbrev: str = ""
    group: str = ""
    pub_date: str = ""
    abstract: str = ""
    abstract_src: str = ""
    sources: set = field(default_factory=set)
    score: int = 0
    item_hash: str = ""
    kr_summary: str = ""

    @classmethod
    def from_row(cls, r) -> "Paper":
        return cls(doi=r["doi"], title=r["title"] or "", authors=[a for a in (r["authors"] or "").split(" | ") if a],
                   journal=r["journal"] or "", abbrev=r["abbrev"] or "", group=r["grp"] or "", pub_date=r["pub_date"] or "",
                   abstract=r["abstract"] or "", abstract_src=r["abstract_src"] or "", score=r["score"] or 0,
                   item_hash=r["item_hash"] or "", kr_summary=r["kr_summary"] or "")

    @property
    def authors_str(self) -> str:
        a = [x for x in self.authors if x]
        if len(a) > 4:
            return ", ".join(a[:3]) + f" 외 {len(a) - 3}명"
        return ", ".join(a)


def excluded(title: str) -> bool:
    t = (title or "").strip()
    return (not t) or any(p.search(t) for p in EXCLUDE)


def rebuild_abstract(inv) -> str:
    """OpenAlex abstract_inverted_index → 평문."""
    if not inv:
        return ""
    pos = sorted((p, w) for w, ps in inv.items() for p in ps)
    return clean_abstract(" ".join(w for _, w in pos))


@lru_cache(maxsize=512)
def _kw_regex(kw: str):
    """기본은 단어 전체(+복수형 s/es) 일치. 끝에 *를 붙이면 앞부분 일치 (예: rent* → rental)."""
    kw = str(kw).strip().lower()
    if not kw:
        return None
    if kw.endswith("*"):
        return re.compile(r"(?<![a-z0-9])" + re.escape(kw[:-1]))
    return re.compile(r"(?<![a-z0-9])" + re.escape(kw) + r"(?:s|es)?(?![a-z0-9])")


def score(p: Paper, keywords: list[str]) -> int:
    text = f"{p.title} {p.abstract}".lower()
    return sum(1 for kw in keywords if (rx := _kw_regex(kw)) and rx.search(text))


def _cr_date(d) -> str:
    try:
        parts = [int(x) for x in d["date-parts"][0] if x is not None]
        parts += [1] * (3 - len(parts))
        return date(parts[0], parts[1], parts[2]).isoformat()
    except Exception:  # noqa: BLE001
        return ""


class Collector:
    def __init__(self, http: Http | None = None):
        self.http = http or Http()
        self.oa_key = os.environ.get("OPENALEX_API_KEY", "").strip()
        self.errors: list[str] = []

    def openalex(self, j: dict, since: date) -> list[Paper]:
        params = {
            "filter": f"primary_location.source.issn:{j['issn'][0]},from_publication_date:{since.isoformat()}",
            "select": "doi,title,authorships,publication_date,abstract_inverted_index,type",
            "per-page": PAGE, "cursor": "*",
        }
        if self.oa_key:
            params["api_key"] = self.oa_key
        out: list[Paper] = []
        for _ in range(MAX_PAGES):
            data = self.http.get_json(OPENALEX, params)
            if data is None:
                self.errors.append(f"OpenAlex:{j['abbrev']}")
                break
            results = data.get("results") or []
            out += [p for w in results if (p := self.from_openalex(w, j))]
            nxt = (data.get("meta") or {}).get("next_cursor")
            if not results or not nxt or len(results) < PAGE:
                break
            params["cursor"] = nxt
        return out

    @staticmethod
    def from_openalex(w: dict, j: dict) -> Paper | None:
        if (w.get("type") or "") in BAD_TYPES:
            return None
        doi, title = norm_doi(w.get("doi")), clean_title(w.get("title"))
        if not doi or excluded(title):
            return None
        authors = [n for a in w.get("authorships") or [] if (n := ((a or {}).get("author") or {}).get("display_name"))]
        ab = rebuild_abstract(w.get("abstract_inverted_index"))
        return Paper(doi=doi, title=title, authors=authors, journal=j["name"], abbrev=j["abbrev"], group=j.get("group", ""),
                     pub_date=w.get("publication_date") or "", abstract=ab, abstract_src="OpenAlex" if ab else "",
                     sources={"openalex"})

    def crossref(self, j: dict, since: date) -> list[Paper]:
        params = {
            "filter": f"issn:{j['issn'][0]},from-created-date:{since.isoformat()},type:journal-article",
            "select": "DOI,title,author,created,issued,abstract,published-online,published-print",
            "rows": PAGE, "cursor": "*",
        }
        out: list[Paper] = []
        for _ in range(MAX_PAGES):
            data = self.http.get_json(CROSSREF, params)
            if data is None:
                self.errors.append(f"Crossref:{j['abbrev']}")
                break
            msg = data.get("message") or {}
            items = msg.get("items") or []
            out += [p for it in items if (p := self.from_crossref(it, j))]
            nxt = msg.get("next-cursor")
            if not items or not nxt or len(items) < PAGE:
                break
            params["cursor"] = nxt
        return out

    @staticmethod
    def from_crossref(it: dict, j: dict) -> Paper | None:
        doi = norm_doi(it.get("DOI"))
        title = clean_title((it.get("title") or [""])[0] if it.get("title") else "")
        if not doi or excluded(title):
            return None
        authors = [n for a in it.get("author") or []
                   if (n := " ".join(x for x in (a.get("given"), a.get("family")) if x) or a.get("name") or "")]
        pub = (_cr_date(it.get("published-online")) or _cr_date(it.get("issued")) or _cr_date(it.get("published-print"))
               or ((it.get("created") or {}).get("date-time") or "")[:10])
        ab = clean_abstract(it.get("abstract"))
        return Paper(doi=doi, title=title, authors=authors, journal=j["name"], abbrev=j["abbrev"], group=j.get("group", ""),
                     pub_date=pub, abstract=ab, abstract_src="Crossref" if ab else "", sources={"crossref"})

    def collect(self, j: dict, since: date) -> list[Paper]:
        merged: dict[str, Paper] = {}
        for p in self.crossref(j, since) + self.openalex(j, since):
            m = merged.get(p.doi)
            if m is None:
                merged[p.doi] = p
                continue
            m.sources |= p.sources
            if not m.abstract and p.abstract:
                m.abstract, m.abstract_src = p.abstract, p.abstract_src
            if len(p.authors) > len(m.authors):
                m.authors = p.authors
            if not m.pub_date:
                m.pub_date = p.pub_date
        return [p for p in merged.values() if p.authors or p.abstract]

    def collect_all(self, journals: list[dict], since: date) -> list[Paper]:
        seen: dict[str, Paper] = {}
        for j in journals:
            for p in self.collect(j, since):
                seen.setdefault(p.doi, p)
        return list(seen.values())
