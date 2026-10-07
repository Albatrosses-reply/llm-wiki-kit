"""초록 한글 요약. AI 호출 수를 줄이려고 여러 편을 JSON으로 묶어 한 번에 요청한다(읽기 전용 실행)."""
from __future__ import annotations

import json
import logging
import re

from . import config as C
from . import llm

log = logging.getLogger("wikikit")
BATCH = 12
HANGUL = re.compile(r"[가-힣]")

PROMPT = """아래 JSON 배열의 각 논문 초록을 한국어 2~3문장으로 요약하라.
연구 질문, 자료·방법, 핵심 발견을 담고 부동산·경제·경영 전공 학생이 빨리 파악할 수 있게 쓴다. 수식어와 머리말 없이 요약문만.
파일을 읽거나 명령을 실행하지 말고, 아래 형식의 JSON 객체 하나만 출력하라(코드 블록 표시 없이): {{"<id>": "<요약>", ...}}

{items}"""


def parse(out: str) -> dict:
    m = re.search(r"\{.*\}", out or "", re.S)
    if not m:
        return {}
    try:
        d = json.loads(m.group(0))
    except ValueError:
        return {}
    return {str(k): str(v).strip() for k, v in d.items() if isinstance(v, str) and HANGUL.search(v)}


def summarize(papers: list, cfg: dict, store) -> int:
    todo = [p for p in sorted(papers, key=lambda p: -(p.score or 0)) if p.abstract and not p.kr_summary][: int(cfg.get("max_summaries", 40))]
    done = 0
    C.TMP.mkdir(parents=True, exist_ok=True)
    for i in range(0, len(todo), BATCH):
        chunk = todo[i:i + BATCH]
        items = json.dumps([{"id": p.item_hash, "title": p.title, "abstract": p.abstract[:2000]} for p in chunk], ensure_ascii=False)
        ok, out = llm.run(cfg, PROMPT.format(items=items), C.TMP, write=False, timeout=600)
        got = parse(out) if ok else {}
        for p in chunk:
            if got.get(p.item_hash):
                p.kr_summary = got[p.item_hash]
                store.update(p.doi, kr_summary=p.kr_summary)
                done += 1
        if not ok:
            log.warning(f"한글 요약 실패: {out[:200]}")
            break
    log.info(f"한글 요약 {done}/{len(todo)}편")
    return done
