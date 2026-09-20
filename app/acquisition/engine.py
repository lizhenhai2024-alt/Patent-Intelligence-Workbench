from __future__ import annotations

from pathlib import Path
from urllib.parse import urlparse

from .base import AcquisitionAdapter, AcquisitionError
from .models import AcquisitionKind, AcquisitionRequest, AcquisitionResult


class AcquisitionEngine:
    def __init__(
        self,
        *,
        web: AcquisitionAdapter,
        files: AcquisitionAdapter,
        browser: AcquisitionAdapter | None = None,
    ) -> None:
        self.web = web
        self.files = files
        self.browser = browser

    async def acquire(self, request: AcquisitionRequest) -> AcquisitionResult:
        kind = request.kind or self._infer_kind(request)
        if kind is AcquisitionKind.FILE:
            return await self.files.acquire(request)
        if kind is AcquisitionKind.BROWSER or request.prefer_browser:
            if self.browser is None:
                raise AcquisitionError("Browser acquisition adapter is not configured.")
            return await self.browser.acquire(request)
        if kind is AcquisitionKind.WEB:
            return await self.web.acquire(request)
        raise AcquisitionError(f"Unsupported acquisition kind: {kind}")

    @staticmethod
    def _infer_kind(request: AcquisitionRequest) -> AcquisitionKind:
        source = request.source.strip()
        parsed = urlparse(source)
        if parsed.scheme in {"http", "https"}:
            return AcquisitionKind.WEB
        if parsed.scheme == "file":
            return AcquisitionKind.FILE
        if not parsed.scheme and Path(source).exists():
            return AcquisitionKind.FILE
        raise AcquisitionError(f"Unsupported acquisition source: {source}")
