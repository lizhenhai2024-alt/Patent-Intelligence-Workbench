from __future__ import annotations

import asyncio
from pathlib import Path
from urllib.parse import unquote, urlparse

from .base import AcquisitionError
from .models import AcquisitionKind, AcquisitionRequest, AcquisitionResult


class MarkItDownAdapter:
    async def acquire(self, request: AcquisitionRequest) -> AcquisitionResult:
        path = self._path(request.source)
        if not path.exists():
            raise AcquisitionError(f"File not found: {path}")
        try:
            return await asyncio.to_thread(self._convert, path)
        except Exception as exc:
            raise AcquisitionError(f"MarkItDown failed for {path}: {exc}") from exc

    @staticmethod
    def _path(source: str) -> Path:
        parsed = urlparse(source)
        if parsed.scheme == "file":
            return Path(unquote(parsed.path.lstrip("/")))
        return Path(source)

    @staticmethod
    def _convert(path: Path) -> AcquisitionResult:
        try:
            from markitdown import MarkItDown
        except ImportError as exc:
            raise AcquisitionError(
                "MarkItDown is not installed. Install the acquisition extra."
            ) from exc
        converted = MarkItDown().convert(str(path))
        text = converted.text_content or ""
        return AcquisitionResult(
            source=str(path),
            kind=AcquisitionKind.FILE,
            markdown=text,
            metadata={"path": str(path)},
        )
