"""Desktop entry point."""

from __future__ import annotations

import argparse

from app.desktop.paths import AppPaths
from app.desktop.runtime import DesktopRuntime


def smoke_test() -> int:
    runtime = DesktopRuntime.create()
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

    if args.data_dir:
        paths = AppPaths(
            root=__import__("pathlib").Path(args.data_dir),
            library_db=__import__("pathlib").Path(args.data_dir) / "patent_library.db",
            watch_db=__import__("pathlib").Path(args.data_dir) / "patent_watch.db",
            downloads=__import__("pathlib").Path(args.data_dir) / "downloads",
            exports=__import__("pathlib").Path(args.data_dir) / "exports",
        )
        runtime = DesktopRuntime.create(paths)
        if args.smoke:
            runtime.close()
            return 0
        from app.desktop.app import run_desktop

        run_desktop(runtime)
        return 0

    if args.smoke:
        return smoke_test()

    from app.desktop.app import run_desktop

    run_desktop()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
