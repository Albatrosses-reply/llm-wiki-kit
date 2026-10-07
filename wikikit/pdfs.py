"""PDF: 다운로드 폴더나 raw/pdf/에 둔 PDF를 고른 논문과 DOI로 맞추고, 쪽 번호가 붙은 텍스트로 바꾼다(raw/text/).

유료 논문 PDF를 자동으로 내려받지는 않는다. 사람이 학교 도서관 등으로 받아 두면 연결만 한다.
"""
from __future__ import annotations

import logging
import re
import shutil
import time
from pathlib import Path

from .util import norm_doi

log = logging.getLogger("wikikit")
DOI_RE = re.compile(r"10\.\d{4,9}/[^\s\"<>]+", re.I)
RECENT_DAYS = 30


def pages(pdf: Path, limit: int | None = None) -> list[str]:
    try:
        from pypdf import PdfReader
    except ImportError:
        log.warning("pypdf가 없어 PDF를 읽지 못함 (python install.py로 설치)")
        return []
    try:
        r = PdfReader(str(pdf))
        return [(pg.extract_text() or "") for pg in r.pages[:limit]]
    except Exception as e:  # noqa: BLE001
        log.warning(f"PDF 읽기 실패 {pdf.name}: {e}")
        return []


def dois_in(text: str) -> set[str]:
    return {norm_doi(d.rstrip(".,;)]}")) for d in DOI_RE.findall(text or "")}


def to_text(pdf: Path, out: Path) -> int:
    ps = pages(pdf)
    if ps:
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text("".join(f"\n=== PDF p. {i} ===\n{t}\n" for i, t in enumerate(ps, 1)), encoding="utf-8")
    return len(ps)


def attach(cfg: dict, store) -> list[str]:
    """PDF가 아직 없는 고른 논문에 PDF를 붙인다. 붙인 인용키 목록."""
    vault = cfg["vault_path"]
    want = {r["doi"]: r for r in store.starred("citekey IS NOT NULL AND (pdf_path IS NULL OR pdf_path='')")}
    if not want:
        return []
    done = []
    pdf_dir = vault / "raw" / "pdf"
    pdf_dir.mkdir(parents=True, exist_ok=True)
    for doi, r in list(want.items()):  # ① 사람이 raw/pdf/<인용키>.pdf로 직접 넣은 것
        p = pdf_dir / f"{r['citekey']}.pdf"
        if p.exists():
            store.update(doi, pdf_path=str(p))
            done.append(r["citekey"])
            want.pop(doi)
    dl = Path(cfg.get("downloads", "")).expanduser()
    if want and dl.is_dir():  # ② 다운로드 폴더의 최근 PDF를 첫 두 쪽의 DOI로 맞춤
        cutoff = time.time() - RECENT_DAYS * 86400
        for f in sorted(dl.glob("*.pdf"), key=lambda x: -x.stat().st_mtime):
            if f.stat().st_mtime < cutoff:
                break
            hit = next((d for d in dois_in("\n".join(pages(f, 2))) if d in want), None)
            if not hit:
                continue
            r = want.pop(hit)
            dest = pdf_dir / f"{r['citekey']}.pdf"
            shutil.move(str(f), dest)
            store.update(hit, pdf_path=str(dest))
            done.append(r["citekey"])
            log.info(f"PDF 연결: {f.name} → raw/pdf/{dest.name}")
            if not want:
                break
    return done
