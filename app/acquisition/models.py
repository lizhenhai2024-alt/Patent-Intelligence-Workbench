from __future__ import annotations

from dataclasses import dataclass, field
from enum import StrEnum


class AcquisitionKind(StrEnum):
    WEB = "web"
    FILE = "file"
    BROWSER = "browser"


@dataclass(slots=True)
class AcquisitionRequest:
    source: str
    kind: AcquisitionKind | None = None
    prefer_browser: bool = False


@dataclass(slots=True)
class AcquisitionResult:
    source: str
    kind: AcquisitionKind
    markdown: str
    title: str | None = None
    metadata: dict[str, object] = field(default_factory=dict)
