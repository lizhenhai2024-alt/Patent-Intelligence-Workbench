import asyncio

from app.core.patent_number import normalize_patent_number
from app.downloads.base import DownloadError, PdfPayload
from app.downloads.manager import DownloadManager


class FailingProvider:
    name = "FAIL"

    def __init__(self):
        self.calls = 0

    def supports(self, publication):
        return True

    async def fetch_pdf(self, publication):
        self.calls += 1
        raise DownloadError("source unavailable")


class InvalidProvider:
    name = "INVALID"

    def supports(self, publication):
        return True

    async def fetch_pdf(self, publication):
        return PdfPayload(
            provider=self.name,
            source_url="https://invalid.example",
            data=b"<html>not a pdf</html>",
        )


class SuccessProvider:
    name = "SUCCESS"

    def __init__(self):
        self.calls = 0

    def supports(self, publication):
        return True

    async def fetch_pdf(self, publication):
        self.calls += 1
        return PdfPayload(
            provider=self.name,
            source_url="https://example.test/document.pdf",
            data=b"%PDF-1.7\nunit-test\n%%EOF",
        )


def test_manager_falls_back_after_provider_failure(tmp_path):
    failing = FailingProvider()
    success = SuccessProvider()
    manager = DownloadManager([failing, success])
    publication = normalize_patent_number("US20240123456A1")
    destination = tmp_path / "US20240123456A1.pdf"

    result = asyncio.run(manager.download(publication, destination))

    assert result.provider == "SUCCESS"
    assert destination.read_bytes().startswith(b"%PDF-")
    assert result.attempts[0].provider == "FAIL"
    assert result.attempts[0].error == "source unavailable"
    assert result.attempts[1].provider == "SUCCESS"


def test_manager_rejects_non_pdf_and_uses_next_provider(tmp_path):
    success = SuccessProvider()
    manager = DownloadManager([InvalidProvider(), success])
    publication = normalize_patent_number("JP2024000123A")

    result = asyncio.run(
        manager.download(publication, tmp_path / "JP2024000123A.pdf")
    )

    assert result.provider == "SUCCESS"
    assert "non-PDF payload" in (result.attempts[0].error or "")


def test_existing_valid_pdf_is_used_as_cache(tmp_path):
    success = SuccessProvider()
    destination = tmp_path / "EP1000000A1.pdf"
    destination.write_bytes(b"%PDF-1.4\ncached\n%%EOF")
    manager = DownloadManager([success])
    publication = normalize_patent_number("EP1000000A1")

    result = asyncio.run(manager.download(publication, destination))

    assert result.from_cache is True
    assert result.provider == "LOCAL_CACHE"
    assert success.calls == 0
