import os

import pytest

from app.desktop.credentials import (
    DesktopCredentialStore,
    EnvironmentCredentialStore,
    EpoOpsCredentials,
)


def test_environment_store_reads_epo_credentials(monkeypatch):
    monkeypatch.setenv("EPO_OPS_KEY", "key-1")
    monkeypatch.setenv("EPO_OPS_SECRET", "secret-1")

    credentials = EnvironmentCredentialStore().load_epo_ops()

    assert credentials == EpoOpsCredentials(
        consumer_key="key-1",
        consumer_secret="secret-1",
        source="environment",
    )


def test_environment_store_does_not_persist_credentials():
    store = EnvironmentCredentialStore()

    assert store.persistent_available is False
    with pytest.raises(RuntimeError):
        store.save_epo_ops("key", "secret")


def test_desktop_store_falls_back_to_environment(monkeypatch):
    monkeypatch.setenv("EPO_OPS_KEY", "env-key")
    monkeypatch.setenv("EPO_OPS_SECRET", "env-secret")
    store = DesktopCredentialStore()
    monkeypatch.setattr(store.windows, "load_epo_ops", lambda: None)

    credentials = store.load_epo_ops()

    assert credentials is not None
    assert credentials.consumer_key == "env-key"
    assert credentials.source == "environment"


def test_windows_persistence_flag_matches_platform():
    store = DesktopCredentialStore()
    assert store.persistent_available is (os.name == "nt")
