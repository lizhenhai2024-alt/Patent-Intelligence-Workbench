from datetime import UTC, date, datetime, timedelta

from app.domain.family import FamilyType, PatentFamily, PatentPublication, PriorityClaim
from app.library.models import LibraryQuery
from app.library.store import SQLitePatentLibrary


def _family():
    priority = PriorityClaim(
        number="JP2022000456",
        country="JP",
        priority_date=date(2022, 3, 4),
    )
    return PatentFamily(
        family_type=FamilyType.DOCDB_SIMPLE,
        source="EPO_OPS",
        source_family_id="F-100",
        members=[
            PatentPublication(
                publication_number="JP2024000123A",
                jurisdiction="JP",
                kind_code="A",
                application_number="JP2023000123",
                title="Electronically controlled damper",
                publication_date=date(2024, 1, 15),
                original_assignees=("Test Japan Ltd.",),
                priorities=(priority,),
            ),
            PatentPublication(
                publication_number="US20240123456A1",
                jurisdiction="US",
                kind_code="A1",
                title="Electronically controlled damper",
                publication_date=date(2024, 5, 2),
                current_assignees=("Test US LLC",),
                priorities=(priority,),
            ),
        ],
    )


def test_family_upsert_preserves_first_seen_and_updates_last_seen(tmp_path):
    library = SQLitePatentLibrary(tmp_path / "library.db")
    first = datetime(2026, 9, 20, 8, 0, tzinfo=UTC)
    second = first + timedelta(days=1)

    family_key = library.upsert_family(_family(), seen_at=first)
    library.upsert_family(_family(), seen_at=second)

    patent = library.get_patent("JP2024000123A")
    assert patent is not None
    assert patent.family_key == family_key
    assert patent.source_family_id == "F-100"
    assert patent.earliest_priority_number == "JP2022000456"
    assert patent.first_seen_at == first
    assert patent.last_seen_at == second

    families = library.list_families()
    assert families[0].member_count == 2
    assert families[0].first_seen_at == first
    assert families[0].last_seen_at == second
    library.close()


def test_library_relations_pdf_favorite_note_and_filters(tmp_path):
    library = SQLitePatentLibrary(tmp_path / "library.db")
    library.upsert_family(_family())

    number = "JP2024000123A"
    library.add_company_group(number, "astemo")
    library.add_technology_topic(number, "pilot_control_valve")
    library.add_project(number, "双阀研究")
    library.add_tag(number, "重点")
    library.add_watch_source(
        number,
        "core-astemo-damper",
        event_type="NEW_FAMILY",
    )
    library.attach_pdf(
        number,
        tmp_path / "JP" / "JP2024000123A.pdf",
        provider="GOOGLE_PATENTS",
        source_url="https://example.test/patent.pdf",
    )
    library.set_favorite(number, True)
    library.set_note(number, "主阀与先导阀结构相关")

    patent = library.get_patent(number)
    assert patent is not None
    assert patent.company_groups == ("astemo",)
    assert patent.technology_topics == ("pilot_control_valve",)
    assert patent.projects == ("双阀研究",)
    assert patent.tags == ("重点",)
    assert patent.watch_rule_ids == ("core-astemo-damper",)
    assert patent.favorite is True
    assert patent.note == "主阀与先导阀结构相关"
    assert patent.pdf_paths[0].name == "JP2024000123A.pdf"

    filtered = library.query(
        LibraryQuery(
            text="先导阀",
            jurisdictions=("JP",),
            company_groups=("astemo",),
            technology_topics=("pilot_control_valve",),
            projects=("双阀研究",),
            tags=("重点",),
            watch_rule_ids=("core-astemo-damper",),
            favorite_only=True,
        )
    )
    assert [item.publication_number for item in filtered] == [number]
    library.close()


def test_duplicate_relations_are_idempotent(tmp_path):
    library = SQLitePatentLibrary(tmp_path / "library.db")
    library.upsert_family(_family())

    number = "JP2024000123A"
    library.add_tag(number, "重点")
    library.add_tag(number, "重点")
    library.add_project(number, "CDC")
    library.add_project(number, "CDC")

    patent = library.get_patent(number)
    assert patent is not None
    assert patent.tags == ("重点",)
    assert patent.projects == ("CDC",)
    library.close()


def test_replace_tags_and_projects_is_transactional_and_deduplicated(tmp_path):
    library = SQLitePatentLibrary(tmp_path / "library.db")
    library.upsert_family(_family())

    number = "JP2024000123A"
    library.add_tag(number, "old")
    library.add_project(number, "old-project")

    library.replace_tags(number, ("重点", "重点", " 结构 "))
    library.replace_projects(number, ("CDC", " 双阀研究 ", "CDC"))

    patent = library.get_patent(number)
    assert patent is not None
    assert patent.tags == ("结构", "重点")
    assert patent.projects == ("CDC", "双阀研究")
    library.close()
