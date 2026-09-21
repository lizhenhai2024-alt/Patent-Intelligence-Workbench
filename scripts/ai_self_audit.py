"""Deterministic self-audit entry point for AI-assisted maintenance."""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
import tempfile
from dataclasses import asdict, dataclass
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


@dataclass(frozen=True, slots=True)
class CheckResult:
    name: str
    ok: bool
    detail: str
    returncode: int = 0


def _run(name: str, command: list[str]) -> CheckResult:
    completed = subprocess.run(
        command,
        cwd=ROOT,
        capture_output=True,
        text=True,
        check=False,
    )
    output = "\n".join(
        part.strip()
        for part in (completed.stdout, completed.stderr)
        if part.strip()
    )
    if len(output) > 5000:
        output = output[-5000:]
    return CheckResult(
        name=name,
        ok=completed.returncode == 0,
        detail=output or "PASS",
        returncode=completed.returncode,
    )


def _invariants() -> list[CheckResult]:
    from app.core.company_registry import CompanyRegistry
    from app.library.archive import safe_folder_name

    results: list[CheckResult] = []
    registry = CompanyRegistry.default()
    group_ids = [group.group_id for group in registry.groups]
    results.append(
        CheckResult(
            "unique_company_group_ids",
            len(group_ids) == len(set(group_ids)),
            f"groups={len(group_ids)} unique={len(set(group_ids))}",
        )
    )
    bad_archive_names = [
        group.group_id
        for group in registry.groups
        if not group.archive_folder_name
        or safe_folder_name(group.archive_folder_name) != group.archive_folder_name
    ]
    results.append(
        CheckResult(
            "safe_company_archive_names",
            not bad_archive_names,
            "invalid=" + ",".join(bad_archive_names) if bad_archive_names else "PASS",
        )
    )

    required_docs = [
        ROOT / "AGENTS.md",
        ROOT / "docs" / "AI_PRODUCT_SPEC.md",
        ROOT / "docs" / "ARCHITECTURE.md",
        ROOT / "docs" / "DOWNLOAD_SOURCES.md",
    ]
    missing = [str(path.relative_to(ROOT)) for path in required_docs if not path.is_file()]
    results.append(
        CheckResult(
            "required_ai_contract_docs",
            not missing,
            "missing=" + ",".join(missing) if missing else "PASS",
        )
    )
    return results


def audit(full: bool) -> list[CheckResult]:
    python = sys.executable
    results = [
        _run("compileall", [python, "-m", "compileall", "-q", "app"]),
        _run("ruff", [python, "-m", "ruff", "check", "app", "tests", "scripts"]),
        _run("git_diff_check", ["git", "diff", "--check"]),
    ]
    results.extend(_invariants())
    if not full:
        return results

    results.append(_run("pytest", [python, "-m", "pytest", "-q"]))
    with tempfile.TemporaryDirectory(prefix="piw-ai-audit-") as temp:
        temp_root = Path(temp)
        results.append(
            _run(
                "desktop_smoke",
                [
                    python,
                    "-m",
                    "app.desktop.main",
                    "--smoke",
                    "--data-dir",
                    str(temp_root / "smoke"),
                ],
            )
        )
        results.append(
            _run(
                "offline_release_acceptance",
                [
                    python,
                    "scripts/release_acceptance.py",
                    "--data-dir",
                    str(temp_root / "acceptance"),
                ],
            )
        )
    return results


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--full",
        action="store_true",
        help="Run the complete deterministic offline audit.",
    )
    parser.add_argument(
        "--report",
        type=Path,
        help="Optional path for the JSON audit report.",
    )
    args = parser.parse_args()

    results = audit(args.full)
    payload = {
        "mode": "full" if args.full else "quick",
        "ok": all(item.ok for item in results),
        "checks": [asdict(item) for item in results],
    }
    rendered = json.dumps(payload, ensure_ascii=False, indent=2)
    print(rendered)
    if args.report:
        args.report.parent.mkdir(parents=True, exist_ok=True)
        args.report.write_text(rendered + "\n", encoding="utf-8")
    return 0 if payload["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
