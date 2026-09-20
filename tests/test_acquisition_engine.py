from __future__ import annotations

from dataclasses import dataclass

import pytest

from app.acquisition import (
    AcquisitionEngine,
    AcquisitionError,
    AcquisitionKind,
    AcquisitionRequest,
    AcquisitionResult,
)


@dataclass
class FakeAdapter:
    kind: AcquisitionKind

    async def acquire(self, request: AcquisitionRequest) -> AcquisitionResult:
        return AcquisitionResult(
            source=request.source,
            kind=self.kind,
            markdown=f"{self.kind}:{request.source}",
        )


@pytest.mark.asyncio
async def test_routes_web_urls_to_web_adapter():
    engine = AcquisitionEngine(
        web=FakeAdapter(AcquisitionKind.WEB),
        files=FakeAdapter(AcquisitionKind.FILE),
        browser=FakeAdapter(AcquisitionKind.BROWSER),
    )
    result = await engine.acquire(AcquisitionRequest("https://example.com"))
    assert result.kind is AcquisitionKind.WEB


@pytest.mark.asyncio
async def test_explicit_browser_preference_routes_browser():
    engine = AcquisitionEngine(
        web=FakeAdapter(AcquisitionKind.WEB),
        files=FakeAdapter(AcquisitionKind.FILE),
        browser=FakeAdapter(AcquisitionKind.BROWSER),
    )
    result = await engine.acquire(
        AcquisitionRequest("https://example.com", prefer_browser=True)
    )
    assert result.kind is AcquisitionKind.BROWSER


@pytest.mark.asyncio
async def test_browser_without_adapter_is_clear_error():
    engine = AcquisitionEngine(
        web=FakeAdapter(AcquisitionKind.WEB),
        files=FakeAdapter(AcquisitionKind.FILE),
    )
    with pytest.raises(AcquisitionError, match="not configured"):
        await engine.acquire(
            AcquisitionRequest("https://example.com", prefer_browser=True)
        )


@pytest.mark.asyncio
async def test_unsupported_source_is_rejected():
    engine = AcquisitionEngine(
        web=FakeAdapter(AcquisitionKind.WEB),
        files=FakeAdapter(AcquisitionKind.FILE),
    )
    with pytest.raises(AcquisitionError, match="Unsupported acquisition source"):
        await engine.acquire(AcquisitionRequest("ftp://example.com/file"))
