from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path


def _restart_in_project_venv() -> None:
    """Use the repository virtual environment even when run with global Python."""
    if os.name != "nt":
        return
    project_python = Path(__file__).resolve().parent / ".venv" / "Scripts" / "python.exe"
    if not project_python.is_file():
        return
    if Path(sys.executable).resolve() == project_python.resolve():
        return
    raise SystemExit(subprocess.call([str(project_python), *sys.argv]))


_restart_in_project_venv()

from analog_flow_guard.app import main  # noqa: E402


if __name__ == "__main__":
    main()
