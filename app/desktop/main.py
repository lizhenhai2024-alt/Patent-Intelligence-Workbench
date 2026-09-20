"""Desktop entry point."""

from __future__ import annotations

import argparse
from pathlib import Path

from app.desktop.paths import AppPaths
from app.desktop.runtime import DesktopRuntime


def paths_from_root(root: str | Path) -> AppPaths:
    base = Path(root).expanduser()
    return AppPaths(
        root=base,
        library_db=base / "patent_library.db",
        watch_db=base / "patent_watch.db",
        downloads=base / "downloads",
        exports=base / "exports",
    )


def smoke_test(paths: AppPaths | None = None) -> int:
    runtime = DesktopRuntime.create(paths)
    try:
        assert runtime.paths.library_db.parent.exists()
        assert runtime.paths.watch_db.parent.exists()
        assert runtime.watch_store.list_rules()
        return 0
    finally:
        runtime.close()


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="patent-intelligence-workbench")
    parser.add_argument(
        "--smoke",
        action="store_true",
        help="Initialize runtime resources/databases and exit without opening UI.",
    )
    parser.add_argument(
        "--data-dir",
        help="Override local application data directory.",
    )
    args = parser.parse_args(argv)

    paths = paths_from_root(args.data_dir) if args.data_dir else None
    if args.smoke:
        return smoke_test(paths)

    runtime = DesktopRuntime.create(paths)
    from app.desktop.app import run_desktop

    run_desktop(runtime)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
