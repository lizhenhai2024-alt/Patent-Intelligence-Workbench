import asyncio

import httpx

from app.core.patent_number import normalize_patent_number
from app.providers.google_patents_search import GooglePatentsSearchProvider


def test_google_reader_document_extracts_sections(monkeypatch):
    html = """
    <meta itemprop="publicationNumber" content="US20240003399A1">
    <meta itemprop="title" content="Pilot controlled damper">
    <meta itemprop="abstract" content="A pilot valve controls damping.">
    <section itemprop="description"><p>Description text.</p></section>
    <section itemprop="claims"><p>1. A damper comprising a pilot valve.</p></section>
    """

    async def fake_get(self, client, url, *, params=None, allow_not_found=False):
        request = httpx.Request("GET", url)
        return httpx.Response(200, text=html, request=request)

    monkeypatch.setattr(GooglePatentsSearchProvider, "_get", fake_get)
    provider = GooglePatentsSearchProvider()
    document = asyncio.run(
        provider.get_reader_document(normalize_patent_number("US20240003399A1"))
    )

    assert document.publication_number == "US20240003399A1"
    assert document.abstract == "A pilot valve controls damping."
    assert document.claims == "1. A damper comprising a pilot valve."
    assert document.description == "Description text."
