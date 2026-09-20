from app.downloads.factory import build_default_download_manager


def test_default_download_chain_prefers_official_ep_then_general_fallback():
    manager = build_default_download_manager()

    assert [provider.name for provider in manager.providers] == [
        "EPO_PUBLICATION_SERVER",
        "GOOGLE_PATENTS",
    ]
    assert manager.source_catalog is not None
