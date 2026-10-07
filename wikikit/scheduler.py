"""예약 실행 등록: macOS launchd, Windows 작업 스케줄러. 두 작업을 만든다.

- daily: 매일 settings.toml의 daily_time에 (위키 작성 → 수집 → 메일). 컴퓨터가 꺼져 있었으면 켜진 뒤 실행
- poll: 30분마다 (메일 회신·Obsidian 체크 확인 → 후보 노트)
"""
from __future__ import annotations

import os
import plistlib
import subprocess
import sys
from pathlib import Path

from . import config as C

LABEL = "com.llmwiki"
WIN_TASK = "LLMWiki"


def venv_python(gui: bool = False) -> Path:
    if C.IS_WIN:
        return C.KIT / ".venv" / "Scripts" / ("pythonw.exe" if gui else "python.exe")
    return C.KIT / ".venv" / "bin" / "python"


def _mac_plist(name: str, args: list[str], when: dict, engine_dir: str) -> dict:
    path = ":".join(x for x in (engine_dir, str(Path.home() / ".local/bin"), "/opt/homebrew/bin", "/usr/local/bin", "/usr/bin", "/bin") if x)
    d = {"Label": f"{LABEL}.{name}", "ProgramArguments": [str(venv_python()), str(C.KIT / "wiki.py"), *args],
         "WorkingDirectory": str(C.KIT), "StandardOutPath": str(C.LOGS / f"{name}.out.log"),
         "StandardErrorPath": str(C.LOGS / f"{name}.err.log"),
         "EnvironmentVariables": {"PATH": path, "HOME": str(Path.home()), "LANG": "en_US.UTF-8", "PYTHONUTF8": "1"}}
    d.update(when)
    return d


def install(cfg: dict) -> list[str]:
    C.LOGS.mkdir(parents=True, exist_ok=True)
    hh, mm = (int(x) for x in str(cfg.get("daily_time", "05:30")).split(":"))
    engine_dir = str(Path(cfg.get("engine_path") or "").parent) if cfg.get("engine_path") else ""
    if C.IS_MAC:
        agents = Path.home() / "Library" / "LaunchAgents"
        agents.mkdir(parents=True, exist_ok=True)
        uid = os.getuid()
        out = []
        for name, args, when in (("daily", ["daily"], {"StartCalendarInterval": {"Hour": hh, "Minute": mm}}),
                                 ("poll", ["poll"], {"StartInterval": 1800, "RunAtLoad": True})):
            p = agents / f"{LABEL}.{name}.plist"
            with open(p, "wb") as f:
                plistlib.dump(_mac_plist(name, args, when, engine_dir), f)
            subprocess.run(["launchctl", "bootout", f"gui/{uid}", str(p)], capture_output=True)
            r = subprocess.run(["launchctl", "bootstrap", f"gui/{uid}", str(p)], capture_output=True, text=True)
            out.append(f"{p.name}: {'등록' if r.returncode == 0 else '실패 ' + (r.stderr or '').strip()}")
        return out
    if C.IS_WIN:
        py, wiki = venv_python(gui=True), C.KIT / "wiki.py"
        ps = f"""
$s = New-ScheduledTaskSettingsSet -StartWhenAvailable -AllowStartIfOnBatteries -DontStopIfGoingOnBatteries -ExecutionTimeLimit (New-TimeSpan -Hours 3)
$a1 = New-ScheduledTaskAction -Execute '{py}' -Argument '"{wiki}" daily' -WorkingDirectory '{C.KIT}'
$t1 = New-ScheduledTaskTrigger -Daily -At '{hh:02d}:{mm:02d}'
Register-ScheduledTask -TaskName '{WIN_TASK}-daily' -Action $a1 -Trigger $t1 -Settings $s -Force | Out-Null
$a2 = New-ScheduledTaskAction -Execute '{py}' -Argument '"{wiki}" poll' -WorkingDirectory '{C.KIT}'
$t2 = New-ScheduledTaskTrigger -Once -At (Get-Date).AddMinutes(1) -RepetitionInterval (New-TimeSpan -Minutes 30)
Register-ScheduledTask -TaskName '{WIN_TASK}-poll' -Action $a2 -Trigger $t2 -Settings $s -Force | Out-Null
'등록 완료'
"""
        r = subprocess.run(["powershell", "-NoProfile", "-ExecutionPolicy", "Bypass", "-Command", ps], capture_output=True, text=True)
        return [(r.stdout or r.stderr).strip()]
    py, wiki = venv_python(), C.KIT / "wiki.py"
    return ["이 운영체제는 자동 등록을 지원하지 않습니다. `crontab -e`에 아래 두 줄을 넣으세요:",
            f"{mm} {hh} * * * {py} {wiki} daily", f"*/30 * * * * {py} {wiki} poll"]


def remove() -> list[str]:
    if C.IS_MAC:
        out = []
        for name in ("daily", "poll"):
            p = Path.home() / "Library" / "LaunchAgents" / f"{LABEL}.{name}.plist"
            subprocess.run(["launchctl", "bootout", f"gui/{os.getuid()}", str(p)], capture_output=True)
            if p.exists():
                p.unlink()
                out.append(f"{p.name} 삭제")
        return out
    if C.IS_WIN:
        for n in ("daily", "poll"):
            subprocess.run(["schtasks", "/Delete", "/TN", f"{WIN_TASK}-{n}", "/F"], capture_output=True)
        return ["작업 스케줄러에서 삭제"]
    return ["crontab -e에서 두 줄을 지우세요"]


def status() -> str:
    if C.IS_MAC:
        r = subprocess.run(["launchctl", "list"], capture_output=True, text=True)
        rows = [x for x in r.stdout.splitlines() if LABEL in x]
        return "\n".join(rows) or "등록된 예약 없음"
    if C.IS_WIN:
        r = subprocess.run(["schtasks", "/Query", "/FO", "LIST"], capture_output=True, text=True, errors="replace")
        return "\n".join(x for x in r.stdout.splitlines() if WIN_TASK in x) or "등록된 예약 없음"
    return "crontab -l로 확인"


if __name__ == "__main__":
    print(status(), file=sys.stderr)
