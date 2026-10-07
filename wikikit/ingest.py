"""위키 페이지 작성: 고른 논문마다 AI(Codex/Claude)를 한 번 돌려 wiki/sources/<인용키>.md를 만들고 결과를 검증·수리한다.

- 대상: 후보 노트가 있고 아직 페이지가 없는 논문 + PDF가 새로 생겨 본문으로 다시 쓸 논문 (실패 3회까지)
- 안전장치: 서지(제목·저자·연도·학술지·DOI)는 수집 정보로 덮어쓴다. 학생이 고쳐 쓴 사람 섹션(llm-draft 표식 없음)은 다시 써도 되살린다.
  보관소 규약 파일(AGENTS.md·CLAUDE.md·index.md·log.md)은 AI가 바꿔도 원래대로 돌린다.
"""
from __future__ import annotations

import json
import logging
import re
from datetime import date
from pathlib import Path

from . import config as C
from . import llm, pdfs
from . import vault as V

log = logging.getLogger("wikikit")
MAX_TRIES = 3
PROTECTED = ("AGENTS.md", "CLAUDE.md", "index.md", "log.md")
REQUIRED = ("Research Question", "연구 방법론", "주요 결과")
HUMAN_HEAD = re.compile(r"^## .*\(사람\)\s*$", re.M)
FM = re.compile(r"\A---\n(.*?)\n---[ \t]*\n?", re.S)

PROMPT = """너는 이 Obsidian 보관소의 사서다. 사람이 지켜보지 않는 자동 작업이다. `AGENTS.md`의 '논문 페이지 쓰기' 규칙에 따라 아래 논문 한 편의 페이지를 만든다.

## 논문 정보 (서지는 이 값만 쓴다)
{meta}

## 읽을 자료
{reading}

## 할 일
1. `wiki/_templates/source.md`의 형식(frontmatter 필드 순서, 섹션 순서와 제목)을 그대로 따라 `wiki/sources/{citekey}.md`를 만든다. 이미 있으면 덮어쓴다.
2. frontmatter: type source, citekey·title·authors·year·venue·doi는 위 값, status: skimmed, confidence: {confidence}, human_sections_done: false,
   read_scope: 실제로 읽은 범위(예: "초록만" 또는 "PDF p.1-4, p.28-30"), summary: 한국어 한 줄 요약, concepts: 연결한 개념 페이지 이름 목록.
3. 사람 섹션 3개(✍️ Contribution · ⚠️ Caveats · 🧭 내 연구와의 관계)는 `<!-- human -->` 줄 바로 아래에
   `<!-- llm-draft: 자동 초안. 고쳐 쓰면 이 줄을 지운다 -->` 줄을 넣고 그 아래 초안을 쓴다.
   - Contribution: 이 논문이 문헌에 더한 것 2~3문장. 저자 주장과 평가를 구분한다.
   - Caveats: 식별·가정·자료의 약점 2~3개.
   - 내 연구와의 관계: `AGENTS.md`의 '내 관심 주제'와 대조해 한두 문장. 연결이 없으면 "관심 주제와 직접 연결 없음"이라고만 쓴다.
4. 나머지 섹션은 읽은 자료에 근거해서만 쓴다. 주장 끝에 (PDF p.N) 또는 (초록)을 붙인다. 초록만 있을 때 초록에 없는 내용은 "초록에 없음"이라고 쓴다.
5. 인용문은 PDF가 있을 때만, 원문 그대로 15단어 이하 2개까지: `> "원문" (PDF p. N)`
6. 개념: `index.md`의 개념 목록에서 맞는 것을 고른다. 꼭 필요한 개념이 없으면 `wiki/_templates/concept.md`로 `wiki/concepts/<영문-소문자-하이픈>.md`(status: stub)를 만든다.
   기존 개념 페이지에는 '## 문헌에서의 쓰임'에 이 논문 한 줄([[{citekey}]])만 덧붙인다.
7. 관련 논문: `wiki/sources/`에 실제로 있는 페이지만 [[인용키]]로 링크한다.
8. `wiki/sources/`와 `wiki/concepts/` 밖의 파일은 만들거나 고치지 않는다. index.md·log.md는 프로그램이 갱신한다.
9. 문체: 한국어, 고유명사·용어는 원문, 과장 형용사 금지.

마지막 줄에 아래 JSON 한 줄만 쓴다:
{{"citekey": "{citekey}", "status": "ok", "concepts": [], "note": "한 문장"}}"""


def split_fm(text: str) -> tuple[dict, str]:
    import yaml
    m = FM.match(text)
    if not m:
        return {}, text
    try:
        meta = yaml.safe_load(m.group(1)) or {}
    except yaml.YAMLError:
        meta = {}
    return (meta if isinstance(meta, dict) else {}), text[m.end():]


def join_fm(meta: dict, body: str) -> str:
    import yaml
    class NoAlias(yaml.SafeDumper):  # 같은 날짜 객체가 두 번 나와도 &id001 같은 별칭을 쓰지 않게(Obsidian이 못 읽음)
        def ignore_aliases(self, data):
            return True

    y = yaml.dump(meta, Dumper=NoAlias, allow_unicode=True, sort_keys=False, default_flow_style=None, width=4096)
    return f"---\n{y}---\n" + (body if body.startswith("\n") else "\n" + body)


def human_sections(body: str) -> dict[str, str]:
    """사람이 직접 쓴 사람 섹션: {제목줄: 본문}. llm-draft 표식이 있거나 비어 있으면 제외."""
    out = {}
    heads = list(HUMAN_HEAD.finditer(body))
    for m in heads:
        nxt = re.search(r"^## ", body[m.end():], re.M)
        content = body[m.end(): m.end() + nxt.start()] if nxt else body[m.end():]
        text = re.sub(r"<!--.*?-->", "", content, flags=re.S).strip()
        if text and "llm-draft" not in content:
            out[m.group(0).strip()] = content
    return out


def restore_human(body: str, keep: dict[str, str]) -> str:
    for head, content in keep.items():
        m = re.search(rf"^{re.escape(head)}\s*$", body, re.M)
        if not m:
            body = body.rstrip() + f"\n\n{head}{content}"
            continue
        nxt = re.search(r"^## ", body[m.end():], re.M)
        end = m.end() + nxt.start() if nxt else len(body)
        body = body[:m.end()] + content.rstrip() + "\n\n" + body[end:].lstrip("\n")
    return body


def fix_page(path: Path, row, read_scope_default: str, today) -> bool:
    text = path.read_text(encoding="utf-8")
    meta, body = split_fm(text)
    if not meta or sum(1 for h in REQUIRED if h in body) < 2:
        return False
    authors = [a for a in (row["authors"] or "").split(" | ") if a]
    meta.update(type="source", citekey=row["citekey"], title=row["title"], authors=authors,
                year=int(row["pub_date"][:4]) if (row["pub_date"] or "")[:4].isdigit() else meta.get("year"),
                venue=row["journal"], doi=row["doi"], human_sections_done=bool(meta.get("human_sections_done", False)),
                updated=today)
    meta.setdefault("status", "skimmed")
    meta.setdefault("read_scope", read_scope_default)
    meta.setdefault("created", today)
    path.write_text(join_fm(meta, body), encoding="utf-8")
    return True


def ingest_one(cfg: dict, store, row) -> tuple[bool, str]:
    vault: Path = cfg["vault_path"]
    ck = row["citekey"]
    page = vault / "wiki" / "sources" / f"{ck}.md"
    old_human, old_created = {}, None
    if page.exists():
        meta, body = split_fm(page.read_text(encoding="utf-8"))
        old_human, old_created = human_sections(body), meta.get("created")
    reading = ["- 초록: 위 '논문 정보'의 abstract"]
    has_pdf = bool(row["pdf_path"]) and Path(row["pdf_path"]).exists()
    if has_pdf:
        txt = vault / "raw" / "text" / f"{ck}.txt"
        n = pdfs.to_text(Path(row["pdf_path"]), txt)
        if n:
            reading.append(f"- PDF 본문(쪽 표시 `=== PDF p. N ===`): `raw/text/{ck}.txt` ({n}쪽). 서론(앞 3~4쪽)과 결론 쪽을 중심으로 읽는다")
        else:
            has_pdf = False
    meta = {"citekey": ck, "title": row["title"], "authors": [a for a in (row["authors"] or "").split(" | ") if a],
            "year": (row["pub_date"] or "")[:4], "venue": row["journal"], "doi": row["doi"], "abstract": row["abstract"] or "(초록 없음)"}
    prompt = PROMPT.format(meta=json.dumps(meta, ensure_ascii=False, indent=1), reading="\n".join(reading),
                           confidence="medium" if has_pdf else "low", citekey=ck)
    backup = {n: (vault / n).read_bytes() for n in PROTECTED if (vault / n).exists()}
    _, out = llm.run(cfg, prompt, vault, write=True, timeout=1200)  # 성공 여부는 결과 페이지로 판단
    for n, b in backup.items():  # 규약 파일 원상 복구
        if (vault / n).read_bytes() != b:
            (vault / n).write_bytes(b)
            log.warning(f"AI가 {n}을 바꿔서 되돌림")
    if not page.exists():
        return False, f"페이지가 만들어지지 않음: {out[-200:] if out else ''}"
    today = date.today()  # date 객체로 넘겨야 YAML에 따옴표 없이 쓰인다
    if not fix_page(page, row, "PDF 본문" if has_pdf else "초록만", today):
        return False, "형식이 맞지 않음(frontmatter 또는 필수 섹션 없음)"
    if old_human or old_created:
        meta2, body2 = split_fm(page.read_text(encoding="utf-8"))
        if old_created:
            meta2["created"] = old_created
        page.write_text(join_fm(meta2, restore_human(body2, old_human)), encoding="utf-8")
    store.update(row["doi"], ingested_at=today.isoformat(), ingested_with_pdf=1 if has_pdf else 0, ingest_error=None)
    V.set_candidate_status(Path(row["note_path"]), "ingested")
    return True, "PDF" if has_pdf else "초록"


def run(cfg: dict, store, limit: int | None = None, only: str = "") -> dict:
    vault: Path = cfg["vault_path"]
    res = {"date": date.today().isoformat(), "new": [], "redone": [], "failed": [], "waiting": 0, "pdf_needed": 0}
    attached = pdfs.attach(cfg, store)
    rows = [r for r in store.starred(f"note_path IS NOT NULL AND ingest_tries < {MAX_TRIES}")
            if (not r["ingested_at"] or (r["pdf_path"] and not r["ingested_with_pdf"])) and (not only or only in (r["citekey"], r["doi"]))]
    cap = int(limit if limit is not None else cfg.get("max_ingest", 5))
    for r in rows[:cap]:
        redo = bool(r["ingested_at"])
        log.info(f"위키 작성: {r['citekey']} ({'PDF로 다시' if redo else '새 논문'})")
        ok, why = ingest_one(cfg, store, r)
        if ok:
            res["redone" if redo else "new"].append(r["citekey"])
            V.log(vault, "ingest", r["citekey"], [f"{'PDF 본문으로 다시 씀' if redo else '새 페이지'} ({why}, {cfg.get('engine')})"])
        else:
            store.update(r["doi"], ingest_tries=(r["ingest_tries"] or 0) + 1, ingest_error=why[:500])
            res["failed"].append(r["citekey"])
            log.warning(f"위키 작성 실패 {r['citekey']}: {why}")
    res["waiting"] = max(0, len(rows) - cap)
    res["pdf_needed"] = len(store.starred("ingested_at IS NOT NULL AND (pdf_path IS NULL OR pdf_path='')"))
    res["pdf_attached"] = attached
    V.build_index(vault)
    C.LAST_RUN.parent.mkdir(parents=True, exist_ok=True)
    C.LAST_RUN.write_text(json.dumps(res, ensure_ascii=False, indent=1), encoding="utf-8")
    return res
