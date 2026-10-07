#!/usr/bin/env python3
"""LLM Wiki 설치. 질문에 답하면 가상환경·설정·Obsidian 보관소·예약 실행까지 만든다.

  python install.py                         # 질문에 하나씩 답하기
  python install.py --answers answers.json  # AI 에이전트용: 미리 정한 답(비밀번호·키는 넣지 않는다)
  python install.py --reconfigure           # 설정만 다시 (가상환경 재설치 없이)

비밀번호·API 키는 설치가 끝난 뒤 사용자가 직접 `python wiki.py secrets`로 넣는다.
"""
from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
import sys
from pathlib import Path

KIT = Path(__file__).resolve().parent
if sys.version_info < (3, 11):
    sys.exit(f"Python 3.11 이상이 필요합니다(지금 {sys.version.split()[0]}). python.org에서 최신 Python을 설치하세요.")
sys.path.insert(0, str(KIT))
from wikikit import config as C  # noqa: E402
from wikikit import llm  # noqa: E402
from wikikit.resolve import resolve  # noqa: E402

REALESTATE = {"핵심+확장": ["realestate_core", "realestate_ext"], "핵심만": ["realestate_core"], "안 받음": []}
GENERAL = [("economics", "경제학 주요 저널 10종(AER·QJE·JPE 등)"), ("finance", "재무 주요 저널 5종(JF·JFE·RFS 등)"),
           ("management", "경영·경영정보 5종(MS·ISR·MISQ 등)")]


def ask(q: str, default: str = "") -> str:
    v = input(f"{q}" + (f" [{default}]" if default else "") + ": ").strip()
    return v or default


def ask_yes(q: str, default: bool) -> bool:
    v = ask(q + " (y/n)", "y" if default else "n").lower()
    return v.startswith("y") or v in ("네", "예", "ㅇ")


def split_list(s) -> list[str]:
    if isinstance(s, list):
        return [str(x).strip() for x in s if str(x).strip()]
    return [x.strip() for x in re.split(r"[,;\n]", s or "") if x.strip()]


def make_venv() -> Path:
    py = KIT / ".venv" / ("Scripts/python.exe" if os.name == "nt" else "bin/python")
    if not py.exists():
        print("· 가상환경 만드는 중 (.venv)")
        subprocess.check_call([sys.executable, "-m", "venv", str(KIT / ".venv")])
    print("· 필요한 패키지 설치 중 (pypdf, pyyaml)")
    subprocess.check_call([str(py), "-m", "pip", "install", "-q", "--disable-pip-version-check", "-r", str(KIT / "requirements.txt")])
    return py


def interview() -> dict:
    print("\n=== LLM Wiki 설정 === (Enter를 누르면 [ ] 안의 기본값)\n")
    a = {}
    a["vault"] = ask("1. Obsidian 보관소 폴더", C.DEFAULTS["vault"])
    found = {e: llm.find(e) for e in llm.ENGINES}
    print("   설치된 AI: " + ", ".join(f"{e}({'있음' if p else '없음'})" for e, p in found.items()))
    a["engine"] = ask("2. 위키를 쓸 AI: codex(ChatGPT) / claude(Claude)", "codex" if found["codex"] or not found["claude"] else "claude")
    a["gmail"] = ask("3. 보내는 Gmail 주소 (앱 비밀번호를 만든 계정)")
    a["recipient"] = ask("4. 메일 받을 주소", a["gmail"])
    a["daily_time"] = ask("5. 매일 실행 시각 (HH:MM)", "05:30")
    a["realestate"] = ask("6. 부동산 저널: 핵심+확장 / 핵심만 / 안 받음", "핵심+확장")
    for key, label in GENERAL:
        a[key] = ask_yes(f"   {label}도 받을까요?", False)
    a["keywords"] = ask("7. 관심 키워드(영어, 쉼표 구분, 끝 *는 앞부분 일치)", ", ".join(C.DEFAULTS["keywords"]))
    if any(a[k] for k, _ in GENERAL):
        a["keyword_filter"] = ask_yes("   경제·재무·경영 저널은 키워드에 맞는 논문만 받을까요?", True)
    a["extra_journals"] = ask("8. 추가 저널(영문 이름이나 ISSN, 쉼표 구분, 없으면 Enter)")
    a["interests"] = ask("9. 내 관심 주제를 한두 문장으로 (위키가 '내 연구와의 관계'를 쓸 때 씀)", "")
    a["zotero"] = ask_yes("10. Zotero가 켜져 있으면 고른 논문을 Zotero에도 넣을까요?", True)
    return a


def apply(a: dict) -> dict:
    engine = a.get("engine", "codex").strip().lower()
    if engine not in llm.ENGINES:
        sys.exit(f"engine은 codex 또는 claude: {engine}")
    groups = list(REALESTATE.get(str(a.get("realestate", "핵심+확장")).strip(), REALESTATE["핵심+확장"]))
    general = [k for k, _ in GENERAL if a.get(k)]
    groups += general
    keywords = split_list(a.get("keywords", C.DEFAULTS["keywords"]))
    extra, failed = [], []
    for q in split_list(a.get("extra_journals", "")):
        j = resolve(q)
        if j:
            extra.append(j)
            print(f"   추가 저널: {q} → {j['name']} ({', '.join(j['issn'])})")
        else:
            failed.append(q)
    if failed:
        print(f"   ⚠️ 찾지 못한 저널: {', '.join(failed)} (설치 후 다시: python install.py --reconfigure)")
    if not groups and not extra:
        sys.exit("저널이 하나도 없습니다. 부동산 묶음이나 다른 분야, 추가 저널 중 하나는 골라야 합니다.")
    if not re.fullmatch(r"\d{1,2}:\d{2}", str(a.get("daily_time", "05:30"))):
        sys.exit("daily_time은 HH:MM 형식이어야 합니다")
    values = {
        "vault": str(Path(a.get("vault") or C.DEFAULTS["vault"]).expanduser()),
        "engine": engine, "engine_path": llm.find(engine), "engine_model": a.get("engine_model", ""),
        "gmail": a.get("gmail", "").strip(), "recipient": (a.get("recipient") or a.get("gmail", "")).strip(),
        "daily_time": str(a.get("daily_time", "05:30")), "groups": groups, "keywords": keywords,
        "keyword_only_groups": general if a.get("keyword_filter", True) and keywords else [],
        "extra_journals": extra, "lookback_days": 10, "max_ingest": int(a.get("max_ingest", 5)),
        "max_summaries": 40, "star_keyword": "WIKI-STAR", "downloads": str(Path.home() / "Downloads"),
        "zotero": bool(a.get("zotero", True)),
    }
    C.save(values)
    return values


def make_vault(values: dict, interests: str) -> None:
    from wikikit import vault as V
    vault = Path(values["vault"])
    vault.mkdir(parents=True, exist_ok=True)
    V.ensure(vault)
    ag = vault / "AGENTS.md"
    t = ag.read_text(encoding="utf-8")
    if "{{INTERESTS}}" in t:
        ag.write_text(t.replace("{{INTERESTS}}", interests.strip() or "(아직 적지 않음. 여기에 관심 주제를 한두 문장으로 적어 두면 AI가 참고한다)"), encoding="utf-8")
    if sys.platform == "darwin" and any(p in str(vault) for p in ("/Documents", "/Desktop", "CloudStorage", "Mobile Documents")):
        print("   ⚠️ macOS는 예약 실행이 문서·데스크탑·iCloud·Google Drive 폴더에 접근하지 못하게 막을 수 있습니다. "
              "자동 실행이 실패하면 보관소를 홈 폴더 바로 아래(예: ~/LLM-Wiki)로 옮기세요.")


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--answers", help="답을 담은 JSON 파일 (AI 에이전트용)")
    ap.add_argument("--reconfigure", action="store_true", help="가상환경은 그대로 두고 설정만 다시")
    ap.add_argument("--no-schedule", action="store_true", help="예약 실행을 등록하지 않음")
    args = ap.parse_args()

    py = KIT / ".venv" / ("Scripts/python.exe" if os.name == "nt" else "bin/python")
    if not args.reconfigure or not py.exists():
        py = make_venv()
    if args.answers:
        a = json.loads(Path(args.answers).read_text(encoding="utf-8"))
        bad = [k for k in a if re.search(r"password|secret|api_?key", k, re.I)]
        if bad:
            sys.exit(f"답 파일에 비밀값을 넣지 마세요({', '.join(bad)}). 설치 후 `python wiki.py secrets`로 직접 입력합니다.")
    else:
        a = interview()
    values = apply(a)
    make_vault(values, a.get("interests", ""))
    print(f"\n✅ 설정 저장: {C.SETTINGS}\n✅ 보관소: {values['vault']}")
    if not values["engine_path"]:
        print(f"⚠️ {values['engine']} 실행 파일을 찾지 못했습니다. 설치·로그인 후 `python install.py --reconfigure`를 다시 실행하세요.")
    if not args.no_schedule:
        out = subprocess.run([str(py), str(KIT / "wiki.py"), "schedule"], capture_output=True, text=True)
        print("✅ 예약 실행: " + (out.stdout or out.stderr).strip().replace("\n", " / "))
    print("\n남은 단계 (직접 실행하세요):")
    print("  1) python wiki.py secrets      ← Gmail 앱 비밀번호와 API 키 입력 (화면에 안 보임)")
    print("  2) python wiki.py test-mail    ← 시험 메일 확인")
    print("  3) python wiki.py daily --days 7   ← 첫 알림 메일 받기 (몇 분 걸림)")
    print("  4) Obsidian → '폴더를 보관소로 열기' → " + values["vault"])
    return 0


if __name__ == "__main__":
    sys.exit(main())
