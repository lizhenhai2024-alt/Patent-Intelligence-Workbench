"""Google Patents PDF discovery/download fallback provider."""

from __future__ import annotations

from dataclasses import dataclass
from html.parser import HTMLParser

import httpx

from app.core.patent_number import PatentNumber
from app.downloads.base import DownloadError, PdfPayload


class _CitationPdfParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.pdf_url: str | None = None

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag.lower() != "meta":
            return
        values = {key.lower(): value for key, value in attrs}
        if values.get("name") == "citation_pdf_url" and values.get("content"):
            self.pdf_url = values["content"]


def parse_citation_pdf_url(html: str) -> str | None:
    parser = _CitationPdfParser()
    parser.feed(html)
    return parser.pdf_url


@dataclass(slots=True)
class GooglePatentsPdfProvider:
    timeout_seconds: float = 60.0
    user_agent: str = "Patent-Intelligence-Workbench/0.1"

    name = "GOOGLE_PATENTS"

    def supports(self, publication: PatentNumber) -> bool:
        return True

    def landing_url(self, publication: PatentNumber) -> str:
        return f"https://patents.google.com/patent/{publication.canonical}/en"

    async def fetch_pdf(self, publication: PatentNumber) -> PdfPayload:
        landing_url = self.landing_url(publication)
        headers = {"User-Agent": self.user_agent}

        try:
            async with httpx.AsyncClient(
                timeout=self.timeout_seconds,
                follow_redirects=True,
                headers=headers,
            ) as client:
                landing = await client.get(landing_url)
                landing.raise_for_status()
                pdf_url = parse_citation_pdf_url(landing.text)
                if not pdf_url:
                    raise DownloadError(
                        f"Google Patents did not expose citation_pdf_url for "
                        f"{publication.canonical}."
                    )
                response = await client.get(pdf_url)
                response.raise_for_status()
        except DownloadError:
            raise
        except httpx.HTTPError as exc:
            raise DownloadError(
                f"Google Patents PDF download failed for {publication.canonical}."
            ) from exc

        return PdfPayload(
            provider=self.name,
            source_url=str(response.url),
            data=response.content,
        )
