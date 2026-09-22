"""Presentation-neutral helpers for opening LocalLibrary patents."""

from __future__ import annotations

from pathlib import Path

from app.domain.family import (
    Classification,
    FamilyType,
    PatentFamily,
    PatentPublication,
    PriorityClaim,
)
from app.domain.search import SearchHit
from app.library.models import LibraryPatent


def library_patent_to_search_hit(patent: LibraryPatent) -> SearchHit:
    """Adapt a rich LocalLibrary record to the Reader/Search hit contract."""
    applicants = patent.current_assignees or patent.original_assignees
    classifications = tuple(
        dict.fromkeys(item.code for item in patent.classifications if item.code)
    )
    return SearchHit(
        publication_number=patent.publication_number,
        jurisdiction=patent.jurisdiction,
        kind_code=patent.kind_code,
        title=patent.title,
        applicants=applicants,
        classifications=classifications,
        publication_date=patent.publication_date,
        source=patent.source or "LOCAL_LIBRARY",
    )


def preferred_library_pdf(patent: LibraryPatent) -> Path | None:
    """Return the first existing PDF/document path for a library patent."""
    candidates = [document.path for document in patent.documents]
    candidates.extend(path for path in patent.pdf_paths if path not in candidates)
    for path in candidates:
        resolved = Path(path)
        if resolved.is_file():
            return resolved
    return None


def preferred_library_folder(
    patent: LibraryPatent,
    *,
    library_root: str | Path,
) -> Path:
    """Prefer the patent's own PDF folder, then a matching archive folder."""
    pdf = preferred_library_pdf(patent)
    if pdf is not None:
        return pdf.parent

    root = Path(library_root)
    if root.exists():
        for path in root.rglob(f"*{patent.publication_number}*.pdf"):
            if path.is_file():
                return path.parent
    return root


def library_metadata_summary(patent: LibraryPatent) -> str:
    """Build a compact, human-readable metadata line for the Library UI."""
    applicants = patent.current_assignees or patent.original_assignees
    applicant_text = " / ".join(applicants[:3]) or "—"
    publication_date = patent.publication_date.isoformat() if patent.publication_date else "—"
    priority_date = (
        patent.earliest_priority_date.isoformat()
        if patent.earliest_priority_date
        else "—"
    )
    family = patent.source_family_id or patent.family_key or "—"
    classifications = ", ".join(
        item.code for item in patent.classifications[:8]
    ) or "—"
    source_types = ", ".join(
        dict.fromkeys(item.source_type for item in patent.provenance)
    ) or patent.source or "—"
    return (
        f"申请人：{applicant_text}    公开日：{publication_date}    "
        f"最早优先权：{priority_date}\n"
        f"Family：{family}    CPC/IPC：{classifications}\n"
        f"来源：{source_types}"
    )


def library_patents_to_family(
    patents: tuple[LibraryPatent, ...],
) -> PatentFamily | None:
    """Reconstruct a provider-neutral PatentFamily from LocalLibrary records."""
    if not patents:
        return None
    first = patents[0]
    if not first.family_type:
        return None
    try:
        family_type = FamilyType(first.family_type)
    except ValueError:
        return None

    members: list[PatentPublication] = []
    for patent in patents:
        members.append(
            PatentPublication(
                publication_number=patent.publication_number,
                jurisdiction=patent.jurisdiction,
                kind_code=patent.kind_code,
                application_number=patent.application_number,
                grant_number=patent.grant_number,
                title=patent.title,
                filing_date=patent.filing_date,
                publication_date=patent.publication_date,
                grant_date=patent.grant_date,
                language=patent.language,
                original_assignees=patent.original_assignees,
                current_assignees=patent.current_assignees,
                priorities=tuple(
                    PriorityClaim(
                        number=item.number,
                        country=item.country,
                        priority_date=item.priority_date,
                        priority_type=item.priority_type,
                    )
                    for item in patent.priorities
                ),
                classifications=tuple(
                    Classification(
                        system=item.system,
                        code=item.code,
                        is_main=item.is_main,
                    )
                    for item in patent.classifications
                ),
            )
        )

    return PatentFamily(
        family_type=family_type,
        source=first.family_source or "LOCAL_LIBRARY",
        source_family_id=first.source_family_id,
        members=members,
    )
