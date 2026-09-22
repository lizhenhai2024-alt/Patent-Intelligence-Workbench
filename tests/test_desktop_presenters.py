from datetime import UTC, datetime
from pathlib import Path

from app.desktop.presenters import patent_row, watch_history_row, watch_rule_row
from app.library.models import LibraryPatent
from app.watch.models import WatchRule
from app.watch.state import WatchRuleState, WatchRunHistory


def test_patent_row_formats_library_record():
    stamp = datetime(2026, 9, 20, 8, 0, tzinfo=UTC)
    patent = LibraryPatent(
        publication_number="JP2024000123A",
        jurisdiction="JP",
        kind_code="A",
        family_key="F1",
        family_type="DOCDB_SIMPLE",
        family_source="TEST",
        source_family_id="F1",
        title="Damper",
        application_number=None,
        grant_number=None,
        publication_date=None,
        earliest_priority_number=None,
        earliest_priority_date=None,
        original_assignees=(),
        current_assignees=(),
        company_groups=("astemo",),
        technology_topics=("pilot_control_valve",),
        projects=(),
        tags=(),
        pdf_paths=(Path("JP2024000123A.pdf"),),
        watch_rule_ids=(),
        first_seen_at=stamp,
        last_seen_at=stamp,
        source="TEST",
        favorite=True,
    )

    row = patent_row(patent)
    assert row[0] == "JP2024000123A"
    assert row[3] == "astemo"
    assert row[4] == "pilot_control_valve"
    assert row[5] == "★"
    assert row[6] == "PDF"


def test_watch_presenters_format_rule_and_history():
    stamp = datetime(2026, 9, 20, 8, 0, tzinfo=UTC)
    rule = WatchRule(
        rule_id="r1",
        name="Astemo · 减振器",
        company_group="astemo",
        cadence_hours=24,
    )
    state = WatchRuleState("r1", stamp, stamp)
    history = WatchRunHistory(
        run_id=1,
        rule_id="r1",
        status="success",
        started_at=stamp,
        completed_at=stamp,
        baseline_created=False,
        searched_hits=3,
        resolved_families=2,
        event_count=1,
        error_count=0,
        fatal_error=None,
    )

    assert watch_rule_row(rule, state)[1] == "启用"
    assert watch_rule_row(rule, state)[2] == "24h"
    assert watch_history_row(history)[3] == "1"
