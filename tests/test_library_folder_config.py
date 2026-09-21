from pathlib import Path

from app.desktop.library_config import load_library_folder, save_library_folder


def test_library_root_persists(tmp_path: Path):
    config = tmp_path / "settings.json"
    default = tmp_path / "default"
    selected = tmp_path / "PatentLibrary"

    assert load_library_folder(config, default).root == default
    save_library_folder(config, selected)
    assert selected.exists()
    assert load_library_folder(config, default).root == selected
