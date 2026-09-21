"""Import an existing filesystem patent collection into SQLite."""

from __future__ import annotations

import csv
import json
import re
from dataclasses import dataclass
from datetime import date
from pathlib import Path

from app.core.technology_classifier import TechnologyClassifier
from app.domain.family import (
    Classification,
    FamilyType,
    PatentFamily,
    PatentPublication,
    PriorityClaim,
)
from app.library.store import SQLitePatentLibrary

_PATENT_RE = re.compile(
    r"(?<![A-Z0-9])([A-Z]{2}\d{6,}[A-Z]\d?)(?![A-Z0-9])",
    re.IGNORECASE,
)
_SKIP_PARTS = {
    "_Duplicates",
    "99_重复文件",
    "90_Related_Art",
    "_Reports",
}
_CATEGORY_NODE_IDS = {
    "01_电控减振器_CDC_电磁阀": ("semi_active", "cdc_cvsa"),
    "02_主动悬架_控制_传感器": ("active_suspension",),
    "03_频率选择_FSD_FRD": ("fsd",),
    "04_阀系_阻尼力发生机构": ("valving",),
    "05_HRS_HCS_行程末端缓冲": ("travel_control",),
    "06_密封_导向_摩擦_活塞杆": ("seal_friction_guidance",),
    "07_结构_连接_安装_车高": ("damper_hardware",),
    "08_制造_装配_工艺_质量": ("materials_manufacturing",),
    "09_传统液压减振器_其他": ("passive_damper",),
}


@dataclass(frozen=True, slots=True)
class LocalPatentImportSummary:
    imported: int
    attached_pdfs: int
    skipped: int
    classified: int = 0
    families: int = 0


@dataclass(frozen=True, slots=True)
class _IndexRow:
    number: str
    title: str | None = None
    filing_date: date | None = None
    publication_date: date | None = None
    assignee: str | None = None
    category: str | None = None
    tag: str | None = None
    relative_path: str | None = None


def _parse_date(value: str) -> date | None:
    text = value.strip()
    if not text:
        return None
    try:
        return date.fromisoformat(text)
    except ValueError:
        return None


def _priority_from_payload(item: dict) -> PriorityClaim | None:
    number = str(item.get("number") or "").strip()
    country = str(item.get("country") or "").strip()
    if not number or not country:
        return None
    return PriorityClaim(
        number=number,
        country=country,
        priority_date=_parse_date(str(item.get("priority_date") or "")),
        priority_type=str(item.get("priority_type") or "").strip() or None,
    )


def _classification_from_payload(item: dict) -> Classification | None:
    system = str(item.get("system") or "").strip()
    code = str(item.get("code") or "").strip()
    if not system or not code:
        return None
    return Classification(system=system, code=code, is_main=bool(item.get("is_main", False)))


def _manifest_member(item: dict) -> PatentPublication | None:
    number = str(item.get("publication_number") or "").strip().upper()
    if not number:
        return None
    priorities = tuple(
        claim
        for raw in item.get("priorities", [])
        if isinstance(raw, dict)
        if (claim := _priority_from_payload(raw)) is not None
    )
    classifications = tuple(
        classification
        for raw in item.get("classifications", [])
        if isinstance(raw, dict)
        if (classification := _classification_from_payload(raw)) is not None
    )
    return PatentPublication(
        publication_number=number,
        jurisdiction=str(item.get("jurisdiction") or number[:2]).upper(),
        kind_code=str(item.get("kind_code") or "").strip() or None,
        application_number=str(item.get("application_number") or "").strip() or None,
        grant_number=str(item.get("grant_number") or "").strip() or None,
        title=str(item.get("title") or "").strip() or None,
        filing_date=_parse_date(str(item.get("filing_date") or "")),
        publication_date=_parse_date(str(item.get("publication_date") or "")),
        grant_date=_parse_date(str(item.get("grant_date") or "")),
        language=str(item.get("language") or "").strip() or None,
        original_assignees=tuple(str(v) for v in item.get("original_assignees", []) if v),
        current_assignees=tuple(str(v) for v in item.get("current_assignees", []) if v),
        priorities=priorities,
        classifications=classifications,
    )


def _pdf_number(path: Path) -> str | None:
    match = _PATENT_RE.search(path.stem.upper())
    return match.group(1) if match else None


def _legacy_title_from_pdf(path: Path, publication_number: str) -> str | None:
    match = re.match(
        rf"^{re.escape(publication_number)}[_ ]+(?P<title>.+)$",
        path.stem,
        flags=re.IGNORECASE,
    )
    if match is None:
        return None
    title = match.group("title").replace("_", " ").strip(" ._-")
    return title or None


def _is_active_path(path: Path, folder: Path) -> bool:
    try:
        parts = path.relative_to(folder).parts[:-1]
    except ValueError:
        return False
    return not any(part in _SKIP_PARTS for part in parts)


def _resolve_index_path(folder: Path, raw_path: str | None) -> Path | None:
    if not raw_path:
        return None
    path = folder / Path(raw_path.replace("\\", "/"))
    return path if path.is_file() and _is_active_path(path, folder) else None


def _load_index_rows(folder: Path) -> dict[str, _IndexRow]:
    rows: dict[str, _IndexRow] = {}
    astemo_index = folder / "ASTEMO_Patent_Index.csv"
    if astemo_index.exists():
        with astemo_index.open("r", encoding="utf-8-sig", newline="") as handle:
            for row in csv.DictReader(handle):
                number = (row.get("Publication") or "").strip().upper()
                if not number:
                    continue
                relative_path = (row.get("Path") or "").strip() or None
                if relative_path and any(
                    part in _SKIP_PARTS
                    for part in Path(relative_path.replace("\\", "/")).parts
                ):
                    continue
                rows[number] = _IndexRow(
                    number=number,
                    category=(row.get("Category") or "").strip() or None,
                    tag=(row.get("Tag") or "").strip() or None,
                    relative_path=relative_path,
                )

    complete_index = folder / "patent_list_complete.csv"
    if complete_index.exists():
        with complete_index.open("r", encoding="utf-8-sig", newline="") as handle:
            for row in csv.DictReader(handle):
                number = (row.get("公开号") or "").strip().upper()
                if not number:
                    continue
                previous = rows.get(number)
                rows[number] = _IndexRow(
                    number=number,
                    title=(row.get("专利名称") or "").strip() or (
                        previous.title if previous else None
                    ),
                    filing_date=_parse_date(row.get("申请日") or ""),
                    publication_date=_parse_date(row.get("公开日") or ""),
                    assignee=(row.get("申请人") or "").strip() or None,
                    category=previous.category if previous else None,
                    tag=previous.tag if previous else None,
                    relative_path=previous.relative_path if previous else None,
                )
    return rows


def _load_family_manifests(folder: Path) -> tuple[PatentFamily, ...]:
    families: list[PatentFamily] = []
    for path in sorted(folder.rglob("family.json")):
        if not _is_active_path(path, folder):
            continue
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
            family_type = FamilyType(payload.get("family_type", FamilyType.DOCDB_SIMPLE.value))
        except (OSError, json.JSONDecodeError, ValueError, TypeError):
            continue

        members = [
            member
            for raw in payload.get("members", [])
            if isinstance(raw, dict)
            if (member := _manifest_member(raw)) is not None
        ]
        if not members:
            earliest_raw = payload.get("earliest_priority")
            earliest = (
                _priority_from_payload(earliest_raw)
                if isinstance(earliest_raw, dict)
                else None
            )
            for index, raw in enumerate(payload.get("downloads", [])):
                if not isinstance(raw, dict):
                    continue
                number = str(raw.get("publication_number") or "").strip().upper()
                if not number:
                    continue
                members.append(
                    PatentPublication(
                        publication_number=number,
                        jurisdiction=str(raw.get("jurisdiction") or number[:2]).upper(),
                        priorities=(earliest,) if earliest is not None and index == 0 else (),
                    )
                )
        if not members:
            continue
        families.append(
            PatentFamily(
                family_type=family_type,
                source=str(payload.get("source") or "LOCAL_FAMILY_MANIFEST"),
                source_family_id=str(payload.get("source_family_id") or "").strip() or None,
                members=members,
            )
        )
    return tuple(families)


def _topics_for(
    row: _IndexRow | None,
    path: Path | None,
    folder: Path,
    classifier: TechnologyClassifier,
) -> tuple[str, ...]:
    topics: list[str] = []
    category = row.category if row else None
    for prefix, node_ids in _CATEGORY_NODE_IDS.items():
        if category and category.startswith(prefix):
            for node_id in node_ids:
                name = classifier.taxonomy.find(node_id).name
                if name not in topics:
                    topics.append(name)
    text_parts = [
        row.tag if row and row.tag else "",
        row.category if row and row.category else "",
    ]
    if path is not None:
        try:
            text_parts.append(path.relative_to(folder).as_posix())
        except ValueError:
            text_parts.append(path.name)
    matches = classifier.classify(
        text=" ".join(part for part in text_parts if part),
        require_domain_context=False,
    )
    for match in matches[:8]:
        if match.name not in topics:
            topics.append(match.name)
    return tuple(topics)


def import_patent_folder(
    store: SQLitePatentLibrary,
    folder: Path,
    *,
    company_group: str | None = None,
    default_assignee: str | None = None,
    dry_run: bool = False,
) -> LocalPatentImportSummary:
    folder = Path(folder)
    classifier = TechnologyClassifier()
    rows = _load_index_rows(folder)
    families = _load_family_manifests(folder)
    manifest_publications = {
        member.publication_number: member
        for family in families
        for member in family.members
    }
    pdfs: dict[str, list[Path]] = {}
    skipped = 0

    for path in sorted(folder.rglob("*.pdf")):
        if not _is_active_path(path, folder):
            skipped += 1
            continue
        number = _pdf_number(path)
        if number is None:
            skipped += 1
            continue
        pdfs.setdefault(number, []).append(path)

    for number, row in rows.items():
        indexed_path = _resolve_index_path(folder, row.relative_path)
        if indexed_path is not None:
            bucket = pdfs.setdefault(number, [])
            if indexed_path not in bucket:
                bucket.insert(0, indexed_path)

    imported = attached = classified = 0
    if not dry_run:
        for family in families:
            store.upsert_family(family)

    for number in sorted(set(rows) | set(pdfs) | set(manifest_publications)):
        row = rows.get(number)
        manifest = manifest_publications.get(number)
        paths = pdfs.get(number, [])
        primary_path = paths[0] if paths else None
        topics = _topics_for(row, primary_path, folder, classifier)
        if topics:
            classified += 1

        if dry_run:
            imported += 1
            attached += len(paths)
            continue

        jurisdiction = manifest.jurisdiction if manifest else number[:2]
        assignee = (row.assignee if row else None) or default_assignee
        title = (row.title if row else None) or (manifest.title if manifest else None)
        if title is None and primary_path is not None:
            title = _legacy_title_from_pdf(primary_path, number)
        original_assignees = (
            (assignee,) if assignee else (manifest.original_assignees if manifest else ())
        )
        publication = PatentPublication(
            publication_number=number,
            jurisdiction=jurisdiction,
            kind_code=manifest.kind_code if manifest else None,
            application_number=manifest.application_number if manifest else None,
            grant_number=manifest.grant_number if manifest else None,
            title=title,
            filing_date=(row.filing_date if row and row.filing_date else None)
            or (manifest.filing_date if manifest else None),
            publication_date=(row.publication_date if row and row.publication_date else None)
            or (manifest.publication_date if manifest else None),
            grant_date=manifest.grant_date if manifest else None,
            language=manifest.language if manifest else None,
            original_assignees=original_assignees,
            current_assignees=manifest.current_assignees if manifest else (),
            priorities=manifest.priorities if manifest else (),
            classifications=manifest.classifications if manifest else (),
        )
        store.upsert_publication(publication, source="LOCAL_PATENT_FOLDER")
        imported += 1
        if company_group:
            store.add_company_group(number, company_group)
        for topic in topics:
            store.add_technology_topic(number, topic)
        if row and row.tag:
            store.add_tag(number, row.tag)

        for path in paths:
            store.attach_pdf(number, path, provider="LOCAL_PATENT_FOLDER")
            attached += 1

    return LocalPatentImportSummary(
        imported=imported,
        attached_pdfs=attached,
        skipped=skipped,
        classified=classified,
        families=len(families),
    )
