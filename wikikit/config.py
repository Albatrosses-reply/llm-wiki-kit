"""설정과 경로.

- 프로그램: 이 저장소(KIT). 가상환경은 KIT/.venv
- 내 설정·자료: 홈 폴더의 .llm-wiki (APP). settings.toml(공개해도 되는 설정), .env(비밀값), state.db, logs/
- 위키 보관소(VAULT): settings.toml의 vault. Obsidian으로 여는 폴더
"""
from __future__ import annotations

import os
import sys
import tomllib
from pathlib import Path

KIT = Path(__file__).resolve().parent.parent
APP = Path(os.environ.get("LLM_WIKI_HOME", Path.home() / ".llm-wiki"))
SETTINGS = APP / "settings.toml"
SECRETS = APP / ".env"
DB = APP / "state.db"
LOGS = APP / "logs"
TMP = APP / "tmp"
LAST_RUN = APP / "last_wiki_run.json"
JOURNALS = KIT / "wikikit" / "journals.toml"
TEMPLATE = KIT / "vault_template"
IS_WIN = sys.platform.startswith("win")
IS_MAC = sys.platform == "darwin"
SECRET_KEYS = ("GMAIL_APP_PASSWORD", "ELSEVIER_API_KEY", "S2_API_KEY")

DEFAULTS = {
    "vault": str(Path.home() / "LLM-Wiki"),
    "engine": "codex",            # codex | claude
    "engine_path": "",            # 설치 때 찾은 실행 파일 경로(예약 실행은 PATH가 짧아서 절대경로로)
    "engine_model": "",           # 비우면 각 도구 기본 모델
    "gmail": "",                  # 보내는 Gmail 주소 (= 회신 받는 주소)
    "recipient": "",              # 받는 주소. 비우면 gmail과 같음
    "daily_time": "05:30",
    "groups": ["realestate_core", "realestate_ext"],
    "keywords": ["housing", "rent*", "mortgage*", "house price*", "real estate", "zoning"],
    "keyword_only_groups": [],
    "extra_journals": [],
    "lookback_days": 10,
    "max_ingest": 5,              # 하루에 위키 페이지로 만들 최대 편수
    "max_summaries": 40,          # 하루 한글 요약 최대 편수
    "star_keyword": "WIKI-STAR",
    "downloads": str(Path.home() / "Downloads"),
    "zotero": True,               # Zotero가 켜져 있으면 고른 논문을 Zotero에도 넣는다
}


def load_env() -> None:
    if not SECRETS.exists():
        return
    for line in SECRETS.read_text(encoding="utf-8").splitlines():
        k, sep, v = line.strip().partition("=")
        if sep and k.strip() and not k.strip().startswith("#"):
            os.environ.setdefault(k.strip(), v.strip().strip('"').strip("'"))


def load() -> dict:
    cfg = dict(DEFAULTS)
    if SETTINGS.exists():
        with open(SETTINGS, "rb") as f:
            cfg.update(tomllib.load(f))
    with open(JOURNALS, "rb") as f:
        cfg["catalog"] = tomllib.load(f).get("groups", {})
    cfg["recipient"] = cfg.get("recipient") or cfg.get("gmail", "")
    cfg["vault_path"] = Path(cfg["vault"]).expanduser()
    load_env()
    return cfg


def secret(name: str) -> str:
    return os.environ.get(name, "").strip()


def journals(cfg: dict) -> list[dict]:
    """고른 묶음의 저널 + 추가 저널. 각 저널에 group·group_label. 첫 ISSN 기준 중복 제거."""
    out, seen = [], set()
    for g in cfg.get("groups", []):
        grp = cfg["catalog"].get(g)
        for j in (grp or {}).get("journals", []):
            out.append({**j, "group": g, "group_label": grp.get("label", g)})
    for j in cfg.get("extra_journals", []):
        out.append({**j, "group": "extra", "group_label": "추가 저널"})
    uniq = []
    for j in out:
        if j.get("issn") and j["issn"][0] not in seen:
            seen.add(j["issn"][0])
            uniq.append(j)
    return uniq


def group_order(cfg: dict) -> list[tuple[str, str]]:
    order = [(g, cfg["catalog"][g].get("label", g)) for g in cfg.get("groups", []) if g in cfg["catalog"]]
    if cfg.get("extra_journals"):
        order.append(("extra", "추가 저널"))
    return order


# ── 쓰기 (설치 마법사용) ──
def _q(s) -> str:
    return '"' + str(s).replace("\\", "\\\\").replace('"', '\\"') + '"'


def _v(v) -> str:
    if isinstance(v, bool):
        return "true" if v else "false"
    if isinstance(v, (int, float)):
        return str(v)
    if isinstance(v, list):
        if v and isinstance(v[0], dict):
            rows = [", ".join(f"{k} = {_v(x)}" for k, x in d.items()) for d in v]
            return "[\n" + "".join(f"  {{ {r} }},\n" for r in rows) + "]"
        return "[" + ", ".join(_q(x) for x in v) + "]"
    return _q(v)


COMMENTS = {
    "vault": "Obsidian 보관소 폴더", "engine": "위키를 쓰는 AI: codex(ChatGPT) 또는 claude(Claude)",
    "gmail": "보내는 Gmail 주소(회신도 이 주소로)", "recipient": "받는 주소(비우면 gmail과 같음)",
    "daily_time": "매일 실행 시각(HH:MM). 바꾸면 `python wiki.py schedule`을 다시 실행",
    "groups": "저널 묶음(wikikit/journals.toml)", "keywords": "관심 키워드. 끝 *는 앞부분 일치",
    "keyword_only_groups": "이 묶음은 키워드에 맞는 논문만", "extra_journals": "추가 저널",
    "max_ingest": "하루 위키 페이지 최대 편수", "zotero": "Zotero가 켜져 있으면 고른 논문을 Zotero에도",
}


def save(values: dict) -> None:
    APP.mkdir(parents=True, exist_ok=True)
    lines = ["# LLM Wiki 설정. 직접 고쳐도 된다. 비밀번호·API 키는 여기 말고 .env (python wiki.py secrets)", ""]
    for k in DEFAULTS:
        if k in values:
            if k in COMMENTS:
                lines.append(f"# {COMMENTS[k]}")
            lines.append(f"{k} = {_v(values[k])}")
    SETTINGS.write_text("\n".join(lines) + "\n", encoding="utf-8")


def save_secrets(values: dict) -> None:
    """비어 있지 않은 값만 바꾸고 나머지는 유지한다. 파일 권한은 본인만 읽기."""
    APP.mkdir(parents=True, exist_ok=True)
    cur = {}
    if SECRETS.exists():
        for line in SECRETS.read_text(encoding="utf-8").splitlines():
            k, sep, v = line.partition("=")
            if sep:
                cur[k.strip()] = v.strip()
    cur.update({k: v for k, v in values.items() if v})
    SECRETS.write_text("".join(f"{k}={v}\n" for k, v in cur.items()), encoding="utf-8")
    try:
        os.chmod(SECRETS, 0o600)
    except OSError:
        pass
