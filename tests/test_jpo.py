import pytest

from app.providers.base import ProviderCapability, ProviderConfigurationError
from app.providers.jpo import API_BASE_URL, TOKEN_URL, JpoProvider


def test_jpo_uses_official_hosts():
    assert TOKEN_URL == "https://ip-data.jpo.go.jp/auth/token"
    assert API_BASE_URL == "https://ip-data.jpo.go.jp/api"


def test_jpo_domestic_provider_does_not_claim_family_capability():
    provider = JpoProvider(username="user", password="password")
    assert ProviderCapability.FAMILY_SIMPLE not in provider.info.capabilities
    assert ProviderCapability.FAMILY_EXTENDED not in provider.info.capabilities


def test_jpo_requires_credentials(monkeypatch):
    monkeypatch.delenv("JPO_API_USERNAME", raising=False)
    monkeypatch.delenv("JPO_API_PASSWORD", raising=False)
    provider = JpoProvider()

    with pytest.raises(ProviderConfigurationError):
        provider._require_credentials()
