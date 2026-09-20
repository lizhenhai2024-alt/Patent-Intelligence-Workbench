"""Default V1 download provider composition."""

from __future__ import annotations

from app.downloads.manager import DownloadManager
from app.downloads.source_catalog import DownloadSourceCatalog
from app.providers.epo_publication_server import EpoPublicationServerProvider
from app.providers.google_patents import GooglePatentsPdfProvider


def build_default_download_manager() -> DownloadManager:
    """Build the V1 default chain.

    EP documents use the official EPO Publication Server first.
    Other jurisdictions currently use Google Patents as the automated
    fallback, while official manual/registered alternatives are exposed
    through the source catalog rather than brittle website scraping.
    """
    return DownloadManager(
        providers=(
            EpoPublicationServerProvider(),
            GooglePatentsPdfProvider(),
        ),
        source_catalog=DownloadSourceCatalog.default(),
    )
