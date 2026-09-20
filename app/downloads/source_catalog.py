"""Official/manual source policy for download fallbacks."""

from __future__ import annotations

import json
from dataclasses import dataclass
from importlib import resources

from app.core.patent_number import PatentNumber
from app.downloads.base import OfficialSourceHint


@dataclass(frozen=True, slots=True)
class DownloadSourceCatalog:
    by_jurisdiction: dict[str, tuple[OfficialSourceHint, ...]]

    @classmethod
    def from_dict(cls, payload: dict) -> DownloadSourceCatalog:
        result: dict[str, tuple[OfficialSourceHint, ...]] = {}
        for jurisdiction, entries in payload.get("jurisdictions", {}).items():
            result[jurisdiction.upper()] = tuple(
                OfficialSourceHint(
                    name=item["name"],
                    url=item["url"],
                    access_mode=item["access_mode"],
                    document_type=item["document_type"],
                    note=item.get("note"),
                )
                for item in entries
            )
        return cls(result)

    @classmethod
    def default(cls) -> DownloadSourceCatalog:
        text = (
            resources.files("app.resources")
            .joinpath("download_sources.json")
            .read_text(encoding="utf-8")
        )
        return cls.from_dict(json.loads(text))

    def hints_for(self, publication: PatentNumber) -> tuple[OfficialSourceHint, ...]:
        return self.by_jurisdiction.get(publication.jurisdiction, ())
