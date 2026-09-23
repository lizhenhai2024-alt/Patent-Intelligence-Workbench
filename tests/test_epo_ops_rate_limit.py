"""EPO OPS enforces per-minute throttling; a bulk backfill can make a few
hundred consecutive calls and trip it. `_authorized_get` retries a bounded
number of times with backoff on HTTP 429 before giving up (see
app/library/search_backfill.py for the caller this protects)."""

from __future__ import annotations

import httpx
import pytest

from app.providers import epo_ops
from app.providers.base import ProviderRateLimitError


def _provider() -> epo_ops.EpoOpsProvider:
    return epo_ops.EpoOpsProvider(consumer_key="k", consumer_secret="s")


@pytest.mark.asyncio
async def test_authorized_get_retries_once_on_429_then_succeeds(monkeypatch):
    sleeps: list[float] = []

    async def fake_sleep(seconds: float) -> None:
        sleeps.append(seconds)

    monkeypatch.setattr(epo_ops.asyncio, "sleep", fake_sleep)

    calls = {"count": 0}

    def handler(request: httpx.Request) -> httpx.Response:
        calls["count"] += 1
        if calls["count"] == 1:
            return httpx.Response(429)
        return httpx.Response(200, text="ok")

    transport = httpx.MockTransport(handler)
    provider = _provider()
    async with httpx.AsyncClient(transport=transport) as client:
        response = await provider._authorized_get(client, "https://example.test/x", token="t")

    assert response.status_code == 200
    assert calls["count"] == 2
    assert sleeps == [epo_ops.RATE_LIMIT_BACKOFF_SECONDS[0]]


@pytest.mark.asyncio
async def test_authorized_get_raises_rate_limit_error_after_exhausting_retries(monkeypatch):
    sleeps: list[float] = []

    async def fake_sleep(seconds: float) -> None:
        sleeps.append(seconds)

    monkeypatch.setattr(epo_ops.asyncio, "sleep", fake_sleep)

    calls = {"count": 0}

    def handler(request: httpx.Request) -> httpx.Response:
        calls["count"] += 1
        return httpx.Response(429)

    transport = httpx.MockTransport(handler)
    provider = _provider()
    async with httpx.AsyncClient(transport=transport) as client:
        with pytest.raises(ProviderRateLimitError):
            await provider._authorized_get(client, "https://example.test/x", token="t")

    assert calls["count"] == 1 + len(epo_ops.RATE_LIMIT_BACKOFF_SECONDS)
    assert sleeps == list(epo_ops.RATE_LIMIT_BACKOFF_SECONDS)


@pytest.mark.asyncio
async def test_authorized_get_does_not_retry_on_success():
    calls = {"count": 0}

    def handler(request: httpx.Request) -> httpx.Response:
        calls["count"] += 1
        return httpx.Response(200, text="ok")

    transport = httpx.MockTransport(handler)
    provider = _provider()
    async with httpx.AsyncClient(transport=transport) as client:
        response = await provider._authorized_get(client, "https://example.test/x", token="t")

    assert response.status_code == 200
    assert calls["count"] == 1
