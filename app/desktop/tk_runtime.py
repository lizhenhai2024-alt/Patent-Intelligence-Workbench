"""Tk runtime capability detection for desktop tests and diagnostics."""

from __future__ import annotations

import os
from functools import lru_cache


@lru_cache(maxsize=1)
def can_run_tk_tests() -> bool:
    if os.environ.get("CI"):
        return False
    try:
        import tkinter as tk
    except (ImportError, ModuleNotFoundError):
        return False

    root = None
    try:
        root = tk.Tk()
        root.withdraw()
        root.update_idletasks()
    except tk.TclError:
        return False
    finally:
        if root is not None:
            try:
                root.destroy()
            except tk.TclError:
                pass
    return True
