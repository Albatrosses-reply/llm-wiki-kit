"""상태 DB(sqlite): 수집한 논문, 메일 발송, 위키 후보 선택, 위키 페이지 작성 상태."""
from __future__ import annotations

import hashlib
import sqlite3
from datetime import datetime, timedelta
from pathlib import Path

from .collect import Paper

SCHEMA = """
CREATE TABLE IF NOT EXISTS papers (
  doi TEXT PRIMARY KEY,
  item_hash TEXT UNIQUE NOT NULL,
  title TEXT, authors TEXT, journal TEXT, abbrev TEXT, grp TEXT, pub_date TEXT,
  abstract TEXT, abstract_src TEXT, kr_summary TEXT, score INTEGER DEFAULT 0,
  first_seen TEXT NOT NULL,
  emailed_at TEXT, digest_at TEXT,
  status TEXT NOT NULL DEFAULT 'pending',      -- pending | starred
  starred_at TEXT, star_via TEXT,
  citekey TEXT, note_path TEXT, zotero_at TEXT,
  pdf_path TEXT, ingested_at TEXT, ingested_with_pdf INTEGER DEFAULT 0, ingest_tries INTEGER DEFAULT 0, ingest_error TEXT
);
CREATE TABLE IF NOT EXISTS seen_mail (msgid TEXT PRIMARY KEY, at TEXT);
"""
ORDER = "ORDER BY grp, abbrev, score DESC, pub_date DESC"


def now() -> str:
    return datetime.now().isoformat(timespec="seconds")


class Store:
    def __init__(self, path):
        Path(path).parent.mkdir(parents=True, exist_ok=True)
        self.c = sqlite3.connect(str(path), timeout=30)
        self.c.row_factory = sqlite3.Row
        self.c.executescript(SCHEMA)

    @staticmethod
    def make_hash(doi: str) -> str:
        return hashlib.sha1(doi.encode("utf-8")).hexdigest()[:12]

    def known(self, doi: str) -> bool:
        return self.c.execute("SELECT 1 FROM papers WHERE doi=?", (doi,)).fetchone() is not None

    def add(self, p: Paper) -> None:
        p.item_hash = self.make_hash(p.doi)
        self.c.execute(
            "INSERT OR IGNORE INTO papers(doi,item_hash,title,authors,journal,abbrev,grp,pub_date,abstract,abstract_src,"
            "kr_summary,score,first_seen) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?)",
            (p.doi, p.item_hash, p.title, " | ".join(p.authors), p.journal, p.abbrev, p.group, p.pub_date,
             p.abstract, p.abstract_src, p.kr_summary, p.score, now()))
        self.c.commit()

    def update(self, doi: str, **fields) -> None:
        if fields:
            cols = ", ".join(f"{k}=?" for k in fields)
            self.c.execute(f"UPDATE papers SET {cols} WHERE doi=?", (*fields.values(), doi))
            self.c.commit()

    def _cutoff(self, days: int) -> str:
        return (datetime.now() - timedelta(days=days)).isoformat(timespec="seconds")

    def papers(self, where: str, args: tuple = ()) -> list[Paper]:
        return [Paper.from_row(r) for r in self.c.execute(f"SELECT * FROM papers WHERE {where} {ORDER}", args)]

    def row(self, doi: str):
        return self.c.execute("SELECT * FROM papers WHERE doi=?", (doi,)).fetchone()

    def unsent(self, days: int = 14) -> list[Paper]:
        return self.papers("emailed_at IS NULL AND first_seen>=?", (self._cutoff(days),))

    def undigested(self, days: int = 14) -> list[Paper]:
        return self.papers("digest_at IS NULL AND first_seen>=?", (self._cutoff(days),))

    def missing_abstract(self, days: int = 14) -> list[Paper]:
        return self.papers("(abstract IS NULL OR abstract='') AND first_seen>=?", (self._cutoff(days),))

    def star(self, item_hash: str, via: str) -> bool:
        cur = self.c.execute("UPDATE papers SET status='starred', starred_at=?, star_via=? WHERE item_hash=? AND status='pending'",
                             (now(), via, (item_hash or "").lower()))
        self.c.commit()
        return cur.rowcount > 0

    def starred(self, where: str = "1=1") -> list:
        return self.c.execute(f"SELECT * FROM papers WHERE status='starred' AND {where} ORDER BY starred_at").fetchall()

    def mail_seen(self, msgid: str) -> bool:
        cur = self.c.execute("INSERT OR IGNORE INTO seen_mail(msgid, at) VALUES(?, ?)", (msgid, now()))
        self.c.commit()
        return cur.rowcount == 0

    def citekeys(self) -> set[str]:
        return {r[0] for r in self.c.execute("SELECT citekey FROM papers WHERE citekey IS NOT NULL")}

    def close(self) -> None:
        self.c.close()
