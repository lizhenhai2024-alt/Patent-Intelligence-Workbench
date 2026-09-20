"""Official European Publication Server PDF provider."""

from __future__ import annotations

from dataclasses import dataclass

import httpx

from app.core.patent_number import PatentNumber
from app.downloads.base import DownloadError, PdfPayload

EPS_PDF_URL = "https://data.epo.org/publication-server/pdf-document"


@dataclass(slots=True)
class EpoPublicationServerProvider:
    timeout_seconds: float = 60.0

    name = "EPO_PUBLICATION_SERVER"

    def supports(self, publication: PatentNumber) -> bool:
        return publication.jurisdiction == "EP" and publication.kind_code is not None

    def pdf_url(self, publication: PatentNumber) -> str:
        if not self.supports(publication):
            raise DownloadError(
                f"EPO Publication Server requires an EP publication with kind code: "
                f"{publication.canonical}"
            )
        number = publication.number_without_kind[2:]
        return (
            f"{EPS_PDF_URL}?cc=EP&pn={number}&ki={publication.kind_code}"
        )

    async def fetch_pdf(self, publication: PatentNumber) -> PdfPayload:
        url = self.pdf_url(publication)
        try:
            async with httpx.AsyncClient(
                timeout=self.timeout_seconds,
                follow_redirects=True,
            ) as client:
                response = await client.get(url)
                response.raise_for_status()
        except httpx.HTTPError as exc:
            raise DownloadError(
                f"EPO Publication Server download failed for {publication.canonical}."
            ) from exc

        return PdfPayload(
            provider=self.name,
            source_url=str(response.url),
            data=response.content,
        )
