"""Version-to-GitHub-release mapping for automated publication."""

from __future__ import annotations

import argparse
import re
import tomllib
from dataclasses import dataclass
from pathlib import Path

_RC_RE = re.compile(r"^(?P<base>\d+\.\d+\.\d+)rc(?P<number>\d+)$")
_STABLE_RE = re.compile(r"^\d+\.\d+\.\d+$")


@dataclass(frozen=True, slots=True)
class ReleaseVersion:
    version: str
    tag: str
    prerelease: bool


def parse_release_version(version: str) -> ReleaseVersion:
    value = version.strip()
    match = _RC_RE.fullmatch(value)
    if match:
        return ReleaseVersion(
            version=value,
            tag=f"v{match.group('base')}-rc.{match.group('number')}",
            prerelease=True,
        )
    if _STABLE_RE.fullmatch(value):
        return ReleaseVersion(
            version=value,
            tag=f"v{value}",
            prerelease=False,
        )
    raise ValueError(
        "Automatic release supports only X.Y.Z or X.Y.ZrcN versions; "
        f"got {version!r}."
    )


def read_project_release_version(path: str | Path = "pyproject.toml") -> ReleaseVersion:
    payload = tomllib.loads(Path(path).read_text(encoding="utf-8"))
    version = payload["project"]["version"]
    return parse_release_version(version)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--pyproject", default="pyproject.toml")
    parser.add_argument("--github-output")
    args = parser.parse_args()

    release = read_project_release_version(args.pyproject)
    lines = (
        f"version={release.version}",
        f"tag={release.tag}",
        f"prerelease={'true' if release.prerelease else 'false'}",
    )

    if args.github_output:
        with Path(args.github_output).open("a", encoding="utf-8") as stream:
            for line in lines:
                stream.write(line + "\n")
    else:
        print("\n".join(lines))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
