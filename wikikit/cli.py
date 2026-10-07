"""명령: python wiki.py <명령>

  daily        매일 작업: 후보 확인 → (Zotero) → 위키 작성 → 신간 수집·초록 보충·한글 요약 → 메일 → Obsidian 목록
  poll         메일 회신·Obsidian 체크 확인 → 후보 노트 (30분마다 자동)
  ingest       지금 바로 위키 페이지 작성 (--key 인용키 로 한 편만)
  test-mail    시험 메일 보내기
  secrets      Gmail 앱 비밀번호·API 키 입력 (화면에 보이지 않음)
  schedule     예약 실행 등록 (--remove 로 해제)
  doctor       설치 상태 점검 (--engine 이면 AI 실행까지 시험)
  index        index.md 다시 만들기
"""
from __future__ import annotations

import argparse
import getpass
import json
import logging
import logging.handlers
import os
import sys
import time
from datetime import date, timedelta

from . import abstracts, curate, ingest, llm, scheduler, summarize, zotero
from . import config as C
from . import vault as V
from .collect import Collector, score
from .mailer import Mailer
from .store import Store

log = logging.getLogger("wikikit")


def setup_logging(verbose: bool = True) -> None:
    C.LOGS.mkdir(parents=True, exist_ok=True)
    fh = logging.handlers.RotatingFileHandler(C.LOGS / "wiki.log", maxBytes=2_000_000, backupCount=3, encoding="utf-8")
    fh.setFormatter(logging.Formatter("%(asctime)s %(levelname)s %(message)s"))
    log.addHandler(fh)
    if verbose:
        sh = logging.StreamHandler(sys.stdout)
        sh.setFormatter(logging.Formatter("%(message)s"))
        log.addHandler(sh)
    log.setLevel(logging.INFO)


class Lock:
    """daily와 poll이 겹치지 않게. 3시간 넘은 잠금은 버린다."""

    def __init__(self, name: str):
        self.path = C.APP / f"{name}.lock"

    def __enter__(self):
        if self.path.exists() and time.time() - self.path.stat().st_mtime < 3 * 3600:
            raise RuntimeError("다른 작업이 실행 중")
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.path.write_text(str(os.getpid()))
        return self

    def __exit__(self, *a):
        self.path.unlink(missing_ok=True)


def need_settings(cfg: dict) -> bool:
    if not C.SETTINGS.exists():
        log.error("설정이 없습니다. 먼저 `python install.py`를 실행하세요.")
        return False
    V.ensure(cfg["vault_path"])
    return True


def cmd_poll(cfg, store) -> dict:
    r = curate.poll(cfg, store)
    if any(r.values()):
        log.info(f"후보 확인: Obsidian 체크 {r['checked']} · 메일 {r['mail']} · 새 후보 노트 {r['new']}")
    return r


def cmd_daily(cfg, store, days: int | None = None, no_mail: bool = False, no_ingest: bool = False) -> int:
    today = date.today().isoformat()
    cmd_poll(cfg, store)
    if cfg.get("zotero", True):
        rows = store.starred("zotero_at IS NULL")
        if rows and zotero.save(rows):
            for r in rows:
                store.update(r["doi"], zotero_at=today)
    if not no_ingest:
        res = ingest.run(cfg, store)
        log.info(f"위키: 새 {len(res['new'])} · PDF로 다시 {len(res['redone'])} · 실패 {len(res['failed'])} · 대기 {res['waiting']}")

    js = C.journals(cfg)
    since = date.today() - timedelta(days=days or int(cfg.get("lookback_days", 10)))
    col = Collector()
    papers = col.collect_all(js, since)
    new = [p for p in papers if not store.known(p.doi)]
    for p in new:
        store.add(p)
    log.info(f"수집: 저널 {len(js)}종 · {len(papers)}편 · 새 논문 {len(new)}편" + (f" · 소스 오류 {', '.join(col.errors[:6])}" if col.errors else ""))

    empty = store.missing_abstract()
    if empty:
        abstracts.fill(empty)
        for p in empty:
            if p.abstract:
                store.update(p.doi, abstract=p.abstract, abstract_src=p.abstract_src)
    kws, only = cfg.get("keywords", []), set(cfg.get("keyword_only_groups", []))
    pending = store.unsent()
    for p in pending:
        p.score = score(p, kws)
        store.update(p.doi, score=p.score)
    skip = [p for p in pending if p.group in only and not p.score]
    for p in skip:
        store.update(p.doi, emailed_at="skip", digest_at="skip")
    pending = [p for p in pending if p not in skip]
    if pending:
        summarize.summarize(pending, cfg, store)
    mailer = Mailer(cfg)
    if pending and not no_mail:
        if mailer.send_digest(pending, today):
            for p in pending:
                store.update(p.doi, emailed_at=today)
    elif not pending and not no_mail and mailer.ready:
        from .mailer import wiki_line
        wl = wiki_line()
        if wl and json.loads(C.LAST_RUN.read_text(encoding="utf-8")).get("date") == today:
            mailer.send_status(today, f"오늘은 새 논문이 없습니다.\n{wl}")
    digest = [p for p in store.undigested() if p.group not in only or p.score]
    if digest:
        path = V.write_alerts(cfg["vault_path"], today, digest, cfg)
        for p in digest:
            store.update(p.doi, digest_at=today)
        log.info(f"Obsidian 목록: {path.name} ({len(digest)}편)")
    return 0


def cmd_secrets() -> int:
    print("값을 붙여 넣고 Enter. 입력은 화면에 보이지 않습니다. 바꾸지 않으려면 그냥 Enter.\n")
    vals = {}
    for k, label in (("GMAIL_APP_PASSWORD", "Gmail 앱 비밀번호(16자리, 띄어쓰기는 상관없음)"),
                     ("ELSEVIER_API_KEY", "Elsevier API 키(선택)"), ("S2_API_KEY", "Semantic Scholar API 키(선택)")):
        v = getpass.getpass(f"{label}: ").strip()
        vals[k] = v.replace(" ", "") if k == "GMAIL_APP_PASSWORD" else v
    C.save_secrets(vals)
    print(f"\n저장했습니다: {C.SECRETS} (본인만 읽기)  →  다음: python wiki.py test-mail")
    return 0


def cmd_doctor(cfg, run_engine: bool) -> int:
    ok = True

    def line(good: bool, msg: str):
        nonlocal ok
        ok &= good
        print(("✅ " if good else "❌ ") + msg)

    line(sys.version_info >= (3, 11), f"Python {sys.version.split()[0]}")
    for mod in ("pypdf", "yaml"):
        try:
            __import__(mod)
            line(True, f"{mod} 설치됨")
        except ImportError:
            line(False, f"{mod} 없음 → python install.py 다시 실행")
    line(C.SETTINGS.exists(), f"설정 파일 {C.SETTINGS}")
    line(cfg["vault_path"].is_dir(), f"보관소 {cfg['vault_path']}")
    path = cfg.get("engine_path") or llm.find(cfg.get("engine", "codex"))
    line(bool(path), f"AI 엔진 {cfg.get('engine')}: {path or '찾지 못함'} {llm.version(path) if path else ''}")
    line(bool(cfg.get("gmail")), f"Gmail 주소: {cfg.get('gmail') or '없음'}")
    line(bool(C.secret("GMAIL_APP_PASSWORD")), "Gmail 앱 비밀번호 " + ("있음" if C.secret("GMAIL_APP_PASSWORD") else "없음 → python wiki.py secrets"))
    print(("✅ " if C.secret("ELSEVIER_API_KEY") else "➖ ") + "Elsevier 키 " + ("있음" if C.secret("ELSEVIER_API_KEY") else "없음(선택)"))
    print(("✅ " if C.secret("S2_API_KEY") else "➖ ") + "Semantic Scholar 키 " + ("있음" if C.secret("S2_API_KEY") else "없음(선택)"))
    print(("✅ " if zotero.ping() else "➖ ") + "Zotero " + ("켜져 있음" if zotero.ping() else "꺼져 있음(선택)"))
    print("예약 실행:\n" + scheduler.status())
    if run_engine and path:
        good, out = llm.run(cfg, '{"ok": true} 를 그대로 출력하라. 다른 말 금지.', C.TMP if C.TMP.exists() else C.APP, timeout=180)
        line(good and "ok" in out, f"AI 실행 시험: {out[:120]!r}")
    return 0 if ok else 1


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(prog="wiki.py", description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)
    d = sub.add_parser("daily")
    d.add_argument("--days", type=int)
    d.add_argument("--no-mail", action="store_true")
    d.add_argument("--no-ingest", action="store_true")
    sub.add_parser("poll")
    i = sub.add_parser("ingest")
    i.add_argument("--key", default="")
    i.add_argument("--max", type=int)
    sub.add_parser("test-mail")
    sub.add_parser("secrets")
    s = sub.add_parser("schedule")
    s.add_argument("--remove", action="store_true")
    dr = sub.add_parser("doctor")
    dr.add_argument("--engine", action="store_true")
    sub.add_parser("index")
    a = ap.parse_args(argv)

    if a.cmd == "secrets":
        return cmd_secrets()
    setup_logging(verbose=a.cmd != "poll" or sys.stdout.isatty())
    cfg = C.load()
    if a.cmd == "doctor":
        return cmd_doctor(cfg, a.engine)
    if a.cmd == "schedule":
        print("\n".join(scheduler.remove() if a.remove else scheduler.install(cfg)))
        return 0
    if not need_settings(cfg):
        return 1
    if a.cmd == "test-mail":
        return 0 if Mailer(cfg).send_test() else 1
    if a.cmd == "index":
        print(f"index.md: {V.build_index(cfg['vault_path'])}개 항목")
        return 0
    store = Store(C.DB)
    try:
        with Lock("run"):
            if a.cmd == "poll":
                cmd_poll(cfg, store)
            elif a.cmd == "ingest":
                cmd_poll(cfg, store)
                r = ingest.run(cfg, store, limit=a.max, only=a.key)
                print(json.dumps(r, ensure_ascii=False, indent=1))
            elif a.cmd == "daily":
                return cmd_daily(cfg, store, a.days, a.no_mail, a.no_ingest)
    except RuntimeError as e:
        log.info(f"건너뜀: {e}")
    finally:
        store.close()
    return 0
