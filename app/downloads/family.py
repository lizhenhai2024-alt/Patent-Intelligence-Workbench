"""Download all selected members of a patent family."""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass
from pathlib import Path

from app.core.patent_number import PatentNumberError, normalize_patent_number
from app.domain.family import PatentFamily
from app.downloads.base import DownloadError
from app.downloads.manager import DownloadManager
from app.downloads.naming import family_folder_name, patent_pdf_filename


@dataclass(frozen=True, slots=True)
class FamilyMemberDownload:
    publication_number: str
    jurisdiction: str
    status: str
    path: str | None = None
    provider: str | None = None
    source_url: str | None = None
    error: str | None = None
    from_cache: bool = False


@dataclass(frozen=True, slots=True)
class FamilyDownloadSummary:
    family_folder: Path
    manifest_path: Path
    members: tuple[FamilyMemberDownload, ...]

    @property
    def succeeded(self) -> int:
        return sum(member.status == "success" for member in self.members)

    @property
    def failed(self) -> int:
        return sum(member.status == "failed" for member in self.members)


class FamilyDownloader:
    def __init__(self, manager: DownloadManager):
        self.manager = manager

    async def download_family(
        self,
        family: PatentFamily,
        root: str | Path,
        *,
        jurisdictions: tuple[str, ...] = (),
        retry_failed_only: bool = False,
    ) -> FamilyDownloadSummary:
        earliest = family.earliest_priority
        representative = (
            family.members[0].publication_number if family.members else None
        )
        folder = Path(root) / family_folder_name(
            source_family_id=family.source_family_id,
            earliest_priority_number=earliest.number if earliest else None,
            representative_publication=representative,
        )
        manifest_path = folder / "family.json"
        previous = _load_manifest(manifest_path) if retry_failed_only else {}

        results: list[FamilyMemberDownload] = []
        allowed = {value.upper() for value in jurisdictions}

        for member in family.members:
            if allowed and member.jurisdiction.upper() not in allowed:
                continue

            previous_item = previous.get(member.publication_number)
            if previous_item and previous_item.get("status") == "success":
                results.append(
                    FamilyMemberDownload(
                        publication_number=member.publication_number,
                        jurisdiction=member.jurisdiction,
                        status="success",
                        path=previous_item.get("path"),
                        provider=previous_item.get("provider") or "LOCAL_CACHE",
                        source_url=previous_item.get("source_url"),
                        from_cache=True,
                    )
                )
                continue

            try:
                publication = normalize_patent_number(member.publication_number)
            except PatentNumberError as exc:
                results.append(
                    FamilyMemberDownload(
                        publication_number=member.publication_number,
                        jurisdiction=member.jurisdiction,
                        status="failed",
                        error=str(exc),
                    )
                )
                continue

            destination = (
                folder
                / member.jurisdiction.upper()
                / patent_pdf_filename(publication.canonical)
            )

            try:
                result = await self.manager.download(publication, destination)
            except DownloadError as exc:
                results.append(
                    FamilyMemberDownload(
                        publication_number=member.publication_number,
                        jurisdiction=member.jurisdiction,
                        status="failed",
                        error=str(exc),
                    )
                )
                continue

            results.append(
                FamilyMemberDownload(
                    publication_number=member.publication_number,
                    jurisdiction=member.jurisdiction,
                    status="success",
                    path=str(result.path),
                    provider=result.provider,
                    source_url=result.source_url,
                    from_cache=result.from_cache,
                )
            )

        summary = FamilyDownloadSummary(
            family_folder=folder,
            manifest_path=manifest_path,
            members=tuple(results),
        )
        _write_manifest(family, summary)
        return summary


def _load_manifest(path: Path) -> dict[str, dict]:
    if not path.is_file():
        return {}
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    return {
        item["publication_number"]: item
        for item in payload.get("downloads", [])
        if item.get("publication_number")
    }


def _write_manifest(
    family: PatentFamily,
    summary: FamilyDownloadSummary,
) -> None:
    summary.family_folder.mkdir(parents=True, exist_ok=True)
    earliest = family.earliest_priority
    payload = {
        "family_type": family.family_type.value,
        "source": family.source,
        "source_family_id": family.source_family_id,
        "earliest_priority": (
            {
                "number": earliest.number,
                "country": earliest.country,
                "priority_date": (
                    earliest.priority_date.isoformat()
                    if earliest.priority_date
                    else None
                ),
            }
            if earliest
            else None
        ),
        "downloads": [asdict(member) for member in summary.members],
    }
    summary.manifest_path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
