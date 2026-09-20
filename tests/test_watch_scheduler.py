import asyncio
from datetime import UTC, datetime, timedelta

from app.watch.models import WatchRule, WatchRunResult
from app.watch.scheduler import PatentWatchScheduler
from app.watch.state import SQLiteWatchStateStore


class FakeEngine:
    def __init__(self, store):
        self.state_store = store
        self.calls = []
        self.fail = set()

    async def run_rule(self, rule, *, now=None, page_size=100, max_pages=10):
        self.calls.append(rule.rule_id)
        if rule.rule_id in self.fail:
            raise RuntimeError(f"boom:{rule.rule_id}")
        result = WatchRunResult(
            rule_id=rule.rule_id,
            baseline_created=False,
            searched_hits=0,
            resolved_families=0,
            events=(),
            errors=(),
            started_at=now,
            completed_at=now,
        )
        self.state_store.mark_run(rule.rule_id, now)
        self.state_store.record_run(result)
        return result


def test_due_rules_respect_cadence_and_enabled_flag(tmp_path):
    store = SQLiteWatchStateStore(tmp_path / "watch.db")
    now = datetime(2026, 9, 20, 8, 0, tzinfo=UTC)

    due = WatchRule(
        rule_id="due",
        name="Due",
        company_group="a",
        cadence_hours=24,
    )
    not_due = WatchRule(
        rule_id="not-due",
        name="Not due",
        company_group="a",
        cadence_hours=24,
    )
    disabled = WatchRule(
        rule_id="disabled",
        name="Disabled",
        company_group="a",
        enabled=False,
    )

    for rule in (due, not_due, disabled):
        store.upsert_rule(rule)

    store.mark_run("due", now - timedelta(hours=25))
    store.mark_run("not-due", now - timedelta(hours=2))

    scheduler = PatentWatchScheduler(FakeEngine(store), store)

    assert [rule.rule_id for rule in scheduler.due_rules(now=now)] == ["due"]
    store.close()


def test_scheduler_isolates_rule_failure_and_records_history(tmp_path):
    store = SQLiteWatchStateStore(tmp_path / "watch.db")
    now = datetime(2026, 9, 20, 8, 0, tzinfo=UTC)

    first = WatchRule("first", "First", "a")
    second = WatchRule("second", "Second", "a")
    store.upsert_rule(first)
    store.upsert_rule(second)

    engine = FakeEngine(store)
    engine.fail.add("first")
    scheduler = PatentWatchScheduler(engine, store)

    result = asyncio.run(scheduler.run_due(now=now))

    assert result.due_rule_ids == ("first", "second")
    assert [failure.rule_id for failure in result.failures] == ["first"]
    assert [run.rule_id for run in result.runs] == ["second"]

    history = store.recent_runs()
    statuses = {(item.rule_id, item.status) for item in history}
    assert ("first", "failure") in statuses
    assert ("second", "success") in statuses
    store.close()
