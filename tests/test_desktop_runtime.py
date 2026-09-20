from app.desktop.main import paths_from_root, smoke_test
from app.desktop.runtime import DesktopRuntime


def test_runtime_without_epo_credentials_keeps_local_features_available(
    monkeypatch,
    tmp_path,
):
    monkeypatch.delenv("EPO_OPS_KEY", raising=False)
    monkeypatch.delenv("EPO_OPS_SECRET", raising=False)
    paths = paths_from_root(tmp_path)

    runtime = DesktopRuntime.create(paths)
    try:
        assert runtime.search_service is None
        assert runtime.family_resolver is None
        assert runtime.watch_scheduler is None
        assert "未配置" in runtime.search_status
        assert runtime.watch_store.list_rules()
        assert runtime.paths.library_db.is_file()
        assert runtime.paths.watch_db.is_file()
    finally:
        runtime.close()


def test_smoke_test_initializes_custom_data_dir(monkeypatch, tmp_path):
    monkeypatch.delenv("EPO_OPS_KEY", raising=False)
    monkeypatch.delenv("EPO_OPS_SECRET", raising=False)
    paths = paths_from_root(tmp_path / "smoke")

    assert smoke_test(paths) == 0
    assert paths.library_db.is_file()
    assert paths.watch_db.is_file()
