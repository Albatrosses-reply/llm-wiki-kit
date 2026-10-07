"""AI 실행: Codex(`codex exec`, ChatGPT 로그인) 또는 Claude Code(`claude -p`, Claude 로그인).

프롬프트는 표준입력으로 넘긴다(Windows .cmd 인자 따옴표 문제를 피함). 한 번에 하나씩 순차 실행한다.
write=True면 작업 폴더(cwd) 안에서 파일을 만들고 고칠 수 있게 하고, False면 읽기만 한다.
"""
from __future__ import annotations

import logging
import os
import shutil
import subprocess
import tempfile
from pathlib import Path

log = logging.getLogger("wikikit")
ENGINES = ("codex", "claude")


def find(engine: str) -> str:
    names = [engine, f"{engine}.cmd", f"{engine}.exe"]
    extra = [Path.home() / ".local/bin", Path("/opt/homebrew/bin"), Path("/usr/local/bin"),
             Path(os.environ.get("APPDATA", "")) / "npm"]
    for n in names:
        p = shutil.which(n)
        if p:
            return p
    for d in extra:
        for n in names:
            if (d / n).exists():
                return str(d / n)
    return ""


def version(path: str) -> str:
    try:
        r = subprocess.run([path, "--version"], capture_output=True, text=True, timeout=30)
        return (r.stdout or r.stderr).strip().splitlines()[0] if r.returncode == 0 else ""
    except (OSError, subprocess.TimeoutExpired, IndexError):
        return ""


def command(engine: str, path: str, cwd: Path, write: bool, model: str = "", out_file: Path | None = None) -> list[str]:
    if engine == "codex":
        cmd = [path, "exec", "--skip-git-repo-check", "--ephemeral", "-C", str(cwd),
               "-s", "workspace-write" if write else "read-only", "-c", "approval_policy=\"never\""]
        if model:
            cmd += ["-m", model]
        if out_file:
            cmd += ["-o", str(out_file)]
        return cmd + ["-"]
    tools = "Read,Write,Edit,Glob,Grep" if write else "Read,Glob,Grep"
    cmd = [path, "-p", "--permission-mode", "acceptEdits" if write else "default", "--allowedTools", tools]
    if model:
        cmd += ["--model", model]
    return cmd


HINTS = (
    ("requires a newer version", "Codex가 오래됐습니다. 터미널에서 `npm install -g @openai/codex@latest` (Homebrew로 설치했다면 `brew upgrade codex`) 후 다시 실행하세요."),
    ("not logged in", "AI 도구에 로그인되어 있지 않습니다. 터미널에서 codex(또는 claude)를 한 번 열어 로그인하세요."),
    ("/login", "AI 도구 로그인이 만료됐습니다. 터미널에서 codex(또는 claude)를 열어 다시 로그인하세요."),
    ("usage limit", "AI 사용 한도에 걸렸습니다. 한도가 풀리면 다음 실행에서 이어서 합니다."),
)


def hint(text: str) -> str:
    low = (text or "").lower()
    return next((h for k, h in HINTS if k.lower() in low), "")


def run(cfg: dict, prompt: str, cwd: Path, write: bool = False, timeout: int = 900, model: str = "") -> tuple[bool, str]:
    """(성공, 마지막 응답 텍스트)."""
    engine = cfg.get("engine", "codex")
    path = cfg.get("engine_path") or find(engine)
    if not path:
        return False, f"{engine} 실행 파일을 찾지 못함"
    model = model or cfg.get("engine_model", "")
    out_file = None
    if engine == "codex":
        fd, name = tempfile.mkstemp(prefix="codex-", suffix=".txt")
        os.close(fd)
        out_file = Path(name)
    try:
        flags = getattr(subprocess, "CREATE_NO_WINDOW", 0)  # Windows 예약 실행 때 콘솔 창이 뜨지 않게
        r = subprocess.run(command(engine, path, cwd, write, model, out_file), input=prompt, cwd=str(cwd),
                           capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=timeout,
                           creationflags=flags)
        out = out_file.read_text(encoding="utf-8", errors="replace") if out_file and out_file.exists() else (r.stdout or "")
        if r.returncode != 0:
            tail = (r.stderr or r.stdout or "").strip()[-400:]
            log.warning(f"{engine} 종료 코드 {r.returncode}: {hint(tail) or tail}")
            return False, hint(tail) or out.strip() or tail
        return True, out.strip()
    except subprocess.TimeoutExpired:
        log.warning(f"{engine} 시간 초과({timeout}s)")
        return False, "시간 초과"
    except OSError as e:
        return False, f"{engine} 실행 실패: {e}"
    finally:
        if out_file:
            out_file.unlink(missing_ok=True)
