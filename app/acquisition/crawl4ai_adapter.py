from __future__ import annotations

from .base import AcquisitionError
from .models import AcquisitionKind, AcquisitionRequest, AcquisitionResult


class Crawl4AIAdapter:
    async def acquire(self, request: AcquisitionRequest) -> AcquisitionResult:
        try:
            from crawl4ai import AsyncWebCrawler
        except ImportError as exc:
            raise AcquisitionError(
                "Crawl4AI is not installed. Install the acquisition extra."
            ) from exc
        try:
            async with AsyncWebCrawler() as crawler:
                result = await crawler.arun(url=request.source)
        except Exception as exc:
            raise AcquisitionError(f"Crawl4AI failed for {request.source}: {exc}") from exc
        if not result.success:
            raise AcquisitionError(
                f"Crawl4AI failed for {request.source}: {getattr(result, 'error_message', '')}"
            )
        markdown = getattr(result.markdown, "raw_markdown", None) or str(result.markdown or "")
        return AcquisitionResult(
            source=request.source,
            kind=AcquisitionKind.WEB,
            markdown=markdown,
            title=(result.metadata or {}).get("title"),
            metadata=result.metadata or {},
        )
