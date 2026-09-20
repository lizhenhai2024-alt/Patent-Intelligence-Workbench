from datetime import UTC, date, datetime

from app.domain.family import (
    Classification,
    FamilyType,
    PatentFamily,
    PatentPublication,
    PriorityClaim,
)
from app.domain.search import (
    SearchHit,
    SearchMode,
    SearchPage,
    SearchResponse,
)
from app.downloads.family import FamilyDownloadSummary, FamilyMemberDownload
from app.library.models import LibraryQuery
from app.library.service import PatentLibraryService
from app.library.store import SQLitePatentLibrary
from app.watch.models import WatchEvent, WatchEventType


def test_search_family_download_and_watch_share_one_library_record(tmp_path):
    store = SQLitePatentLibrary(tmp_path / "workbench.db")
    service = PatentLibraryService(store)
    first = datetime(2026, 9, 20, 8, 0, tzinfo=UTC)

    response = SearchResponse(
        mode=SearchMode.COMPANY_TECHNOLOGY,
        provider="EPO_OPS",
        normalized_query="先导阀",
        company_group_id="astemo",
        page=SearchPage(
            hits=(
                SearchHit(
                    publication_number="JP 2024-000123 A",
                    jurisdiction="JP",
                    kind_code="A",
                    title="Damping force control damper",
                    applicants=("Hitachi Astemo, Ltd.",),
                    publication_date=date(2024, 1, 15),
                    source="EPO_OPS",
                ),
            ),
            total_result_count=1,
        ),
    )

    stored = service.ingest_search_response(
        response,
        technology_topics=("pilot_control_valve",),
        projects=("双阀研究",),
        tags=("重点",),
        seen_at=first,
    )
    assert stored == ("JP2024000123A",)

    priority = PriorityClaim(
        number="JP2022000456",
        country="JP",
        priority_date=date(2022, 3, 4),
        priority_type="national",
    )
    family = PatentFamily(
        family_type=FamilyType.DOCDB_SIMPLE,
        source="EPO_OPS",
        source_family_id="F-100",
        members=[
            PatentPublication(
                publication_number="JP2024000123A",
                jurisdiction="JP",
                kind_code="A",
                application_number="JP2023000123",
                title="Damping force control damper",
                filing_date=date(2023, 3, 1),
                publication_date=date(2024, 1, 15),
                language="ja",
                original_assignees=("Hitachi Astemo, Ltd.",),
                priorities=(priority,),
                classifications=(
                    Classification("IPC", "F16F9/46", True),
                    Classification("FI", "F16F9/46", False),
                ),
            )
        ],
    )
    service.ingest_family(
        family,
        company_groups=("astemo",),
        technology_topics=("back_pressure_control",),
        seen_at=datetime(2026, 9, 20, 9, 0, tzinfo=UTC),
    )

    summary = FamilyDownloadSummary(
        family_folder=tmp_path / "downloads",
        manifest_path=tmp_path / "downloads" / "family.json",
        members=(
            FamilyMemberDownload(
                publication_number="JP2024000123A",
                jurisdiction="JP",
                status="success",
                path=str(tmp_path / "downloads" / "JP2024000123A.pdf"),
                provider="GOOGLE_PATENTS",
                source_url="https://example.test/jp.pdf",
            ),
        ),
    )
    assert service.ingest_download_summary(summary) == ("JP2024000123A",)

    event = WatchEvent(
        event_type=WatchEventType.NEW_FAMILY,
        rule_id="core-astemo-damper",
        publication_number="JP2024000123A",
        jurisdiction="JP",
        family_key="DOCDB_SIMPLE:EPO_OPS:F-100",
        family_source_id="F-100",
        title="Damping force control damper",
        publication_date="2024-01-15",
        detected_at=datetime(2026, 9, 20, 10, 0, tzinfo=UTC),
        trigger_publication="JP2024000123A",
    )
    service.ingest_watch_event(
        event,
        company_group="astemo",
        technology_topics=("pilot_control_valve",),
    )

    patent = store.get_patent("JP2024000123A")
    assert patent is not None
    assert patent.application_number == "JP2023000123"
    assert patent.filing_date == date(2023, 3, 1)
    assert patent.language == "ja"
    assert patent.earliest_priority_number == "JP2022000456"
    assert [item.system for item in patent.classifications] == ["FI", "IPC"]
    assert patent.priorities[0].number == "JP2022000456"
    assert patent.company_groups == ("astemo",)
    assert patent.technology_topics == (
        "back_pressure_control",
        "pilot_control_valve",
    )
    assert patent.projects == ("双阀研究",)
    assert patent.tags == ("重点",)
    assert patent.documents[0].provider == "GOOGLE_PATENTS"
    assert patent.watch_rule_ids == ("core-astemo-damper",)

    source_types = {item.source_type for item in patent.provenance}
    assert {"SEARCH", "FAMILY", "DOWNLOAD", "WATCH", "PROVIDER"} <= source_types

    filtered = store.query(
        LibraryQuery(
            source_types=("WATCH",),
            has_pdf=True,
        )
    )
    assert [item.publication_number for item in filtered] == ["JP2024000123A"]
    store.close()


def test_watch_event_can_create_minimal_record_for_new_monitoring_hit(tmp_path):
    store = SQLitePatentLibrary(tmp_path / "workbench.db")
    service = PatentLibraryService(store)
    event = WatchEvent(
        event_type=WatchEventType.NEW_PUBLICATION_UNRESOLVED_FAMILY,
        rule_id="rule-1",
        publication_number="US20240123456A1",
        jurisdiction="US",
        family_key=None,
        family_source_id=None,
        title="Active suspension",
        publication_date="2024-05-02",
        detected_at=datetime(2026, 9, 20, 10, 0, tzinfo=UTC),
        trigger_publication="US20240123456A1",
    )

    number = service.ingest_watch_event(
        event,
        company_group="clearmotion",
        technology_topics=("active_suspension",),
    )

    assert number == "US20240123456A1"
    patent = store.get_patent(number)
    assert patent is not None
    assert patent.company_groups == ("clearmotion",)
    assert patent.technology_topics == ("active_suspension",)
    assert patent.watch_rule_ids == ("rule-1",)
    store.close()
