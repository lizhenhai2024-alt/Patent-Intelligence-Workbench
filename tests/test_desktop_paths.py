from pathlib import Path

from app.desktop.paths import AppPaths


def test_data_dir_override_uses_requested_root(monkeypatch, tmp_path):
    monkeypatch.setenv("PIW_DATA_DIR", str(tmp_path))

    paths = AppPaths.default().ensure()

    assert paths.root == Path(tmp_path)
    assert paths.library_db == Path(tmp_path) / "patent_library.db"
    assert paths.watch_db == Path(tmp_path) / "patent_watch.db"
    assert paths.downloads.is_dir()
    assert paths.exports.is_dir()
