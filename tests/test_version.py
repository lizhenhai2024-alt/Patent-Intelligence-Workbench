from pathlib import Path
import tomllib

from app.version import RELEASE_NAME, RELEASE_TAG, __version__


def test_project_version_matches_application_version():
    root = Path(__file__).resolve().parents[1]
    payload = tomllib.loads((root / "pyproject.toml").read_text(encoding="utf-8"))

    assert payload["project"]["version"] == __version__


def test_rc1_release_metadata_is_consistent():
    assert RELEASE_TAG == "v0.1.0-rc1"
    assert "v0.1.0 RC1" in RELEASE_NAME
    assert __version__ == "0.1.0rc1"
