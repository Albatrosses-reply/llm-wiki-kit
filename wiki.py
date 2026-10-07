#!/usr/bin/env python3
"""LLM Wiki 실행 진입점. 어느 python으로 실행해도 이 폴더의 가상환경(.venv)으로 다시 실행한다.

  python wiki.py doctor        설치 점검
  python wiki.py daily         매일 작업을 지금 실행
  python wiki.py --help        전체 명령
"""
import os
import subprocess
import sys
from pathlib import Path

KIT = Path(__file__).resolve().parent
VENV_PY = KIT / ".venv" / ("Scripts/python.exe" if os.name == "nt" else "bin/python")

if __name__ == "__main__":
    if VENV_PY.exists() and Path(sys.prefix).resolve() != (KIT / ".venv").resolve():
        sys.exit(subprocess.call([str(VENV_PY), str(Path(__file__).resolve()), *sys.argv[1:]]))
    sys.path.insert(0, str(KIT))
    from wikikit.cli import main
    sys.exit(main())
