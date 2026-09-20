from __future__ import annotations

from typing import Protocol

from .models import AcquisitionRequest, AcquisitionResult


class AcquisitionError(RuntimeError):
    pass


class AcquisitionAdapter(Protocol):
    async def acquire(self, request: AcquisitionRequest) -> AcquisitionResult:
        ...
