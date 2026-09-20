from datetime import UTC, datetime

from app.watch.models import WatchRule
from app.watch.state import SQLiteWatchStateStore


def test_watch_state_survives_reopen(tmp_path):
    path = tmp_path / "watch.db"
    rule = WatchRule(
        rule_id="tenneco-valve",
        name="Tenneco valve watch",
        company_group="tenneco",
        technology_terms=("pilot valve",),
    )
    stamp = datetime(2026, 9, 20, 8, 0, tzinfo=UTC)

    store = SQLiteWatchStateStore(path)
    store.upsert_rule(rule)
    store.mark_family(
        rule.rule_id,
        "DOCDB_SIMPLE:TEST:F1",
        family_source_id="F1",
        at=stamp,
    )
    store.mark_publication(
        rule.rule_id,
        "US20240123456A1",
        family_key="DOCDB_SIMPLE:TEST:F1",
        at=stamp,
    )
    store.mark_baselined(rule.rule_id, stamp)
    store.mark_run(rule.rule_id, stamp)
    store.commit()
    store.close()

    reopened = SQLiteWatchStateStore(path)
    assert reopened.get_rule(rule.rule_id) == rule
    assert reopened.family_seen(rule.rule_id, "DOCDB_SIMPLE:TEST:F1")
    assert reopened.publication_seen(rule.rule_id, "US20240123456A1")
    assert (
        reopened.publication_family_key(rule.rule_id, "US20240123456A1")
        == "DOCDB_SIMPLE:TEST:F1"
    )
    assert reopened.get_state(rule.rule_id).baselined_at == stamp
    reopened.close()
