from app.desktop.credentials import EpoOpsCredentials
from app.desktop.main import paths_from_root, smoke_test
from app.desktop.runtime import DesktopRuntime


class FakeCredentialStore:
    def __init__(self, credentials=None):
        self.credentials = credentials
        self.saved = []
        self.deleted = 0

    @property
    def persistent_available(self):
        return True

    def load_epo_ops(self):
        return self.credentials

    def save_epo_ops(self, consumer_key, consumer_secret):
        self.saved.append((consumer_key, consumer_secret))
        self.credentials = EpoOpsCredentials(
            consumer_key=consumer_key,
            consumer_secret=consumer_secret,
            source="windows-credential-manager",
        )

    def delete_epo_ops(self):
        self.deleted += 1
        self.credentials = None


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


def test_runtime_uses_saved_credentials_to_enable_network_services(tmp_path):
    credentials = EpoOpsCredentials(
        consumer_key="key",
        consumer_secret="secret",
        source="windows-credential-manager",
    )
    credential_store = FakeCredentialStore(credentials)
    runtime = DesktopRuntime.create(
        paths_from_root(tmp_path / "configured"),
        credential_store=credential_store,
    )
    try:
        assert runtime.search_service is not None
        assert runtime.family_resolver is not None
        assert runtime.watch_scheduler is not None
        assert "Windows Credential Manager" in runtime.search_status
    finally:
        runtime.close()


def test_runtime_can_save_and_delete_credentials_without_restart(tmp_path):
    credential_store = FakeCredentialStore()
    runtime = DesktopRuntime.create(
        paths_from_root(tmp_path / "settings"),
        credential_store=credential_store,
    )
    try:
        assert runtime.search_service is None

        runtime.save_epo_credentials(" new-key ", " new-secret ")

        assert credential_store.saved == [(" new-key ", " new-secret ")]
        assert runtime.search_service is not None
        assert runtime.credential_source == "windows-credential-manager"

        runtime.delete_epo_credentials()

        assert credential_store.deleted == 1
        assert runtime.search_service is None
        assert runtime.family_resolver is None
        assert runtime.watch_scheduler is None
    finally:
        runtime.close()
