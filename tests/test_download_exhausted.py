import asyncio

import pytest

from app.core.patent_number import normalize_patent_number
from app.downloads.base import DownloadError, DownloadExhaustedError
from app.downloads.manager import DownloadManager
from app.downloads.source_catalog import DownloadSourceCatalog


class AlwaysFailProvider:
    name = "FAIL"

    def supports(self, publication):
        return True

    async def fetch_pdf(self, publication):
        raise DownloadError("network/source failure")


def test_exhausted_download_contains_structured_jp_official_fallbacks(tmp_path):
    manager = DownloadManager(
        [AlwaysFailProvider()],
        source_catalog=DownloadSourceCatalog.default(),
    )
    publication = normalize_patent_number("JP2024000123A")

    with pytest.raises(DownloadExhaustedError) as exc_info:
        asyncio.run(
            manager.download(
                publication,
                tmp_path / "JP2024000123A.pdf",
            )
        )

    error = exc_info.value
    assert error.publication_number == "JP2024000123A"
    assert error.official_sources[0].name == "J-PlatPat"
    assert error.official_sources[0].access_mode == "MANUAL"
