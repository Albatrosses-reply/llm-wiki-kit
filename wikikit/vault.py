"""Obsidian 보관소 쓰기: 일별 체크박스 목록(inbox/alerts), 후보 노트(inbox/starred), 인용키, index.md, log.md."""
from __future__ import annotations

import json
import re
import shutil
import time
import unicodedata
from datetime import date, datetime
from pathlib import Path

from . import config as C
from .mailer import doi_url, grouped

CHECKED = re.compile(r"^\s*[-*+]\s*\[[xX]\].*?hash:([0-9a-f]{12})", re.M)
HASH_IN_LINE = re.compile(r"hash:([0-9a-f]{12})")
UNCHECKED_HEAD = re.compile(r"^(\s*[-*+]\s*)\[ \]")
SCAN_DAYS = 45


def yq(v) -> str:
    return json.dumps(v, ensure_ascii=False)


def md_inline(s: str) -> str:
    return re.sub(r"([\\`*_\[\]])", r"\\\1", s or "")


def ascii_words(s: str) -> list[str]:
    a = unicodedata.normalize("NFKD", s or "").encode("ascii", "ignore").decode()
    return re.findall(r"[A-Za-z0-9]+", a)


def ensure(vault: Path) -> list[str]:
    """템플릿에서 없는 파일만 복사한다(기존 파일은 건드리지 않음). 만든 파일 목록."""
    made = []
    for src in C.TEMPLATE.rglob("*"):
        rel = src.relative_to(C.TEMPLATE)
        dst = vault / rel
        if src.is_dir():
            dst.mkdir(parents=True, exist_ok=True)
        elif not dst.exists() and src.name != ".keep":
            dst.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(src, dst)
            made.append(str(rel))
    for d in ("inbox/alerts", "inbox/starred", "wiki/sources", "wiki/concepts", "wiki/questions", "wiki/syntheses", "raw/pdf", "raw/text"):
        (vault / d).mkdir(parents=True, exist_ok=True)
    return made


# ── 일별 목록 ──
def write_alerts(vault: Path, day: str, papers: list, cfg: dict) -> Path:
    path = vault / "inbox" / "alerts" / f"{day}.md"
    path.parent.mkdir(parents=True, exist_ok=True)
    exists = path.exists()
    lines = ["", f"## 추가분 {datetime.now():%H:%M} ({len(papers)}편)", ""] if exists else [
        "---", "type: journal-alert", f"date: {day}", f"count: {len(papers)}", "---", "",
        f"# 저널 신간 {day} ({len(papers)}편)", "",
        "> 위키에 넣을 논문의 체크박스를 `[x]`로 바꾸면 30분 안에 `inbox/starred/`에 후보 노트가 생기고, 다음 아침 위키 페이지가 만들어진다.", ""]
    h2, h3 = ("###", "####") if exists else ("##", "###")
    for label, journals in grouped(papers, cfg):
        lines.append(f"{h2} {label}")
        for jname, ab, ps in journals:
            lines += ["", f"{h3} {ab} · {jname}"]
            for p in ps:
                lines.append(f"- [ ] **{md_inline(p.title)}**{' ⭐' if p.score else ''} · {md_inline(p.authors_str) or '저자 미상'} · "
                             f"{p.pub_date or '날짜 미상'} · [DOI]({doi_url(p.doi)}) %%hash:{p.item_hash}%%")
                text = p.kr_summary or ((p.abstract[:300] + ("…" if len(p.abstract) > 300 else "")) if p.abstract else "")
                if text:
                    lines.append(f"    > {text}")
        lines.append("")
    with open(path, "a" if exists else "w", encoding="utf-8") as f:
        f.write("\n".join(lines).rstrip() + "\n")
    return path


def _recent_alerts(vault: Path) -> list[Path]:
    d = vault / "inbox" / "alerts"
    cutoff = time.time() - SCAN_DAYS * 86400
    return sorted(f for f in d.glob("*.md") if f.stat().st_mtime >= cutoff) if d.is_dir() else []


def scan_checked(vault: Path) -> list[str]:
    out = []
    for f in _recent_alerts(vault):
        out += [h for h in CHECKED.findall(f.read_text(encoding="utf-8")) if h not in out]
    return out


def mark_checked(vault: Path, hashes: list[str]) -> int:
    want, n = set(hashes), 0
    for f in _recent_alerts(vault):
        lines = f.read_text(encoding="utf-8").split("\n")
        hit = False
        for i, line in enumerate(lines):
            m = HASH_IN_LINE.search(line)
            if m and m.group(1) in want and UNCHECKED_HEAD.match(line):
                lines[i] = UNCHECKED_HEAD.sub(r"\1[x]", line, count=1)
                hit, n = True, n + 1
        if hit:
            f.write_text("\n".join(lines), encoding="utf-8")
    return n


# ── 인용키·후보 노트 ──
def _surname(name: str) -> str:
    name = (name or "").strip()
    sur = name.split(",")[0] if "," in name else (name.split()[-1] if name.split() else "")
    return "".join(w.capitalize() for w in ascii_words(sur))


def make_citekey(authors: list[str], year: str, taken: set[str]) -> str:
    """제1저자 성 + (공저자 1명이면 그 성, 3명 이상이면 EtAl) + 연도. 겹치면 a, b, …"""
    base = _surname(authors[0]) if authors else ""
    base = base or "Anon"
    if len(authors) == 2:
        base += _surname(authors[1])
    elif len(authors) > 2:
        base += "EtAl"
    base += year or "nd"
    key, i = base, 0
    while key in taken:
        key = base + "abcdefghijklmnopqrstuvwxyz"[i % 26] * (i // 26 + 1)
        i += 1
    return key


def write_candidate(vault: Path, row, citekey: str) -> Path:
    d = vault / "inbox" / "starred"
    d.mkdir(parents=True, exist_ok=True)
    path = d / f"{citekey}.md"
    authors = [a for a in (row["authors"] or "").split(" | ") if a]
    fm = ["---", "type: candidate", "status: starred", f"citekey: {yq(citekey)}", f"doi: {yq(row['doi'])}",
          f"title: {yq(row['title'])}", f"authors: {yq(authors)}", f"journal: {yq(row['journal'])}",
          f"pub_date: {yq(row['pub_date'] or '')}", f"starred_at: {yq(row['starred_at'] or '')}", f"star_via: {yq(row['star_via'] or '')}", "---"]
    body = ["", f"# {row['title']}", "", f"{md_inline(', '.join(authors))} · *{row['journal']}* · {row['pub_date'] or ''} · [DOI]({doi_url(row['doi'])})", ""]
    if row["kr_summary"]:
        body += ["## 한글 요약", "", row["kr_summary"], ""]
    body += ["## 초록", "", row["abstract"] or "(초록 미제공)", "",
             "> 다음 아침 자동 처리에서 `wiki/sources/" + citekey + ".md`가 만들어진다. PDF가 있으면 다운로드 폴더에 두거나 `raw/pdf/" + citekey + ".pdf`로 넣으면 본문 기준으로 쓴다.", ""]
    path.write_text("\n".join(fm + body), encoding="utf-8")
    return path


def set_candidate_status(path: Path, status: str) -> None:
    if path and path.exists():
        t = path.read_text(encoding="utf-8")
        path.write_text(re.sub(r"(?m)^status: .*$", f"status: {status}", t, count=1), encoding="utf-8")


# ── index.md · log.md ──
FM = re.compile(r"\A---\n(.*?)\n---", re.S)


def _fm_value(text: str, key: str) -> str:
    m = FM.match(text)
    if not m:
        return ""
    mm = re.search(rf"(?m)^{re.escape(key)}:\s*(.*)$", m.group(1))
    return mm.group(1).strip().strip('"').strip("'") if mm else ""


def build_index(vault: Path) -> int:
    sections = [("wiki/sources", "논문"), ("wiki/concepts", "개념"), ("wiki/questions", "질문"), ("wiki/syntheses", "정리")]
    out = ["# 위키 목록", "", f"자동 생성 {date.today()}. 직접 고치지 않는다(`python wiki.py index`가 다시 만든다).", ""]
    n = 0
    for folder, label in sections:
        files = sorted((vault / folder).glob("*.md"))
        out += [f"## {label} ({len(files)})", ""]
        for f in files:
            t = f.read_text(encoding="utf-8", errors="replace")
            title = _fm_value(t, "title") or f.stem
            summ = _fm_value(t, "summary")
            extra = " · ".join(x for x in (_fm_value(t, "year"), _fm_value(t, "venue") or _fm_value(t, "kind"), _fm_value(t, "status")) if x)
            out.append(f"- [[{f.stem}]] {title}" + (f" ({extra})" if extra else "") + (f" — {summ}" if summ else ""))
            n += 1
        out.append("")
    (vault / "index.md").write_text("\n".join(out), encoding="utf-8")
    return n


def log(vault: Path, kind: str, title: str, lines: list[str]) -> None:
    with open(vault / "log.md", "a", encoding="utf-8") as f:
        f.write(f"\n## [{date.today()}] {kind} | {title}\n" + "".join(f"- {x}\n" for x in lines))
