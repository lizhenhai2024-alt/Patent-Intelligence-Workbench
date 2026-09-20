"""Open local files and folders with the operating-system default handler."""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path


def open_local_path(path: str | Path) -> None:
    target = Path(path)
    if not target.exists():
        raise FileNotFoundError(target)

    if os.name == "nt":
        os.startfile(str(target))  # type: ignore[attr-defined]
        return

    command = ["open", str(target)] if sys.platform == "darwin" else ["xdg-open", str(target)]
    subprocess.Popen(command)  # noqa: S603
