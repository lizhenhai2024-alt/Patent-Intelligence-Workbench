from pathlib import Path

from app.desktop.paths import AppPaths


def test_data_dir_override_uses_unified_database_for_fresh_root(
    monkeypatch,
    tmp_path,
):
    monkeypatch.setenv("PIW_DATA_DIR", str(tmp_path))

    paths = AppPaths.default().ensure()

    assert paths.root == Path(tmp_path)
    assert paths.library_db == Path(tmp_path) / "workbench.db"
    assert paths.watch_db == Path(tmp_path) / "workbench.db"
    assert paths.uses_unified_database is True
    assert paths.downloads.is_dir()
    assert paths.exports.is_dir()


def test_existing_legacy_database_paths_are_preserved(tmp_path):
    legacy_library = tmp_path / "patent_library.db"
    legacy_watch = tmp_path / "patent_watch.db"
    legacy_library.touch()
    legacy_watch.touch()

    paths = AppPaths.for_root(tmp_path)

    assert paths.library_db == legacy_library
    assert paths.watch_db == legacy_watch
    assert paths.uses_unified_database is False


def test_test_session_never_uses_real_app_data():
    """Guard for tests/conftest.py: the default data dir must be a pytest temp dir."""
    import os

    from app.desktop.paths import AppPaths

    assert "piw-app-data" in os.environ["PIW_DATA_DIR"]
    assert "piw-app-data" in str(AppPaths.default().root)
