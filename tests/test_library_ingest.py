from datetime import UTC, datetime
from pathlib import Path

from app.domain.family import FamilyType, PatentFamily, PatentPublication
from app.downloads.family import FamilyDownloadSummary, FamilyMemberDownload
from app.library.ingest import ingest_download_summary, ingest_family, ingest_watch_event
from app.library.store import SQLitePatentLibrary
from app.watch.models import WatchEvent, WatchEventType


def _family():
    return PatentFamily(
        family_type=FamilyType.DOCDB_SIMPLE,
        source="TEST",
        source_family_id="F1",
        members=[
            PatentPublication(
                publication_number="JP2024000123A",
                jurisdiction="JP",
                title="Damper",
            )
        ],
    )


def test_family_ingest_adds_context_and_download_path(tmp_path):
    library = SQLitePatentLibrary(tmp_path / "library.db")
    family = _family()

    ingest_family(
        library,
        family,
        company_group="astemo",
        technology_topics=("pilot_control_valve", "back_pressure_control"),
        project="双阀研究",
        tags=("重点",),
    )

    pdf_path = tmp_path / "downloads" / "JP2024000123A.pdf"
    summary = FamilyDownloadSummary(
        family_folder=tmp_path / "downloads",
        manifest_path=tmp_path / "downloads" / "family.json",
        members=(
            FamilyMemberDownload(
                publication_number="JP2024000123A",
                jurisdiction="JP",
                status="success",
                path=str(pdf_path),
                provider="GOOGLE_PATENTS",
                source_url="https://example.test/document.pdf",
            ),
        ),
    )

    assert ingest_download_summary(library, summary) == 1
    patent = library.get_patent("JP2024000123A")
    assert patent is not None
    assert patent.company_groups == ("astemo",)
    assert patent.technology_topics == (
        "back_pressure_control",
        "pilot_control_valve",
    )
    assert patent.projects == ("双阀研究",)
    assert patent.tags == ("重点",)
    assert patent.pdf_paths == (Path(pdf_path),)
    library.close()


def test_watch_event_links_existing_library_patent(tmp_path):
    library = SQLitePatentLibrary(tmp_path / "library.db")
    ingest_family(library, _family())

    event = WatchEvent(
        event_type=WatchEventType.NEW_FAMILY,
        rule_id="core-astemo-damper",
        publication_number="JP2024000123A",
        jurisdiction="JP",
        family_key="DOCDB_SIMPLE:TEST:F1",
        family_source_id="F1",
        title="Damper",
        publication_date=None,
        detected_at=datetime(2026, 9, 20, 8, 0, tzinfo=UTC),
        trigger_publication="JP2024000123A",
    )

    assert ingest_watch_event(library, event) is True
    patent = library.get_patent("JP2024000123A")
    assert patent is not None
    assert patent.watch_rule_ids == ("core-astemo-damper",)
    library.close()


def test_watch_event_for_unknown_publication_is_not_created_as_partial_record(tmp_path):
    library = SQLitePatentLibrary(tmp_path / "library.db")
    event = WatchEvent(
        event_type=WatchEventType.NEW_FAMILY,
        rule_id="rule-1",
        publication_number="US20240123456A1",
        jurisdiction="US",
        family_key=None,
        family_source_id=None,
        title=None,
        publication_date=None,
        detected_at=datetime(2026, 9, 20, 8, 0, tzinfo=UTC),
        trigger_publication="US20240123456A1",
    )

    assert ingest_watch_event(library, event) is False
    assert library.get_patent("US20240123456A1") is None
    library.close()
