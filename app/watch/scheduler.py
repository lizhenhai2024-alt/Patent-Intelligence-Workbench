"""Run due Patent Watch rules while preserving per-rule failure isolation."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

from app.watch.engine import PatentWatchEngine
from app.watch.models import (
    WatchRule,
    WatchRunFailure,
    WatchSchedulerResult,
)
from app.watch.state import SQLiteWatchStateStore


@dataclass(slots=True)
class PatentWatchScheduler:
    engine: PatentWatchEngine
    state_store: SQLiteWatchStateStore
    failure_retry_hours: int = 1

    def due_rules(self, *, now: datetime | None = None) -> tuple[WatchRule, ...]:
        moment = now or datetime.now(UTC)
        if moment.tzinfo is None:
            raise ValueError("now must be timezone-aware")

        due: list[WatchRule] = []
        for rule in self.state_store.list_rules():
            if not rule.enabled:
                continue
            state = self.state_store.get_state(rule.rule_id)
            last_attempt = self.state_store.last_attempt_at(rule.rule_id)
            if (
                last_attempt is not None
                and (state.last_run_at is None or last_attempt > state.last_run_at)
                and moment - last_attempt < timedelta(hours=self.failure_retry_hours)
            ):
                continue
            if state.last_run_at is None:
                due.append(rule)
                continue
            if moment - state.last_run_at >= timedelta(hours=rule.cadence_hours):
                due.append(rule)
        return tuple(due)

    async def run_due(
        self,
        *,
        now: datetime | None = None,
        page_size: int = 100,
        max_pages: int = 10,
    ) -> WatchSchedulerResult:
        started_at = now or datetime.now(UTC)
        if started_at.tzinfo is None:
            raise ValueError("now must be timezone-aware")

        due = self.due_rules(now=started_at)
        return await self._run_rules(
            due,
            started_at=started_at,
            page_size=page_size,
            max_pages=max_pages,
        )

    async def run_rule_now(
        self,
        rule_id: str,
        *,
        now: datetime | None = None,
        page_size: int = 100,
        max_pages: int = 10,
    ) -> WatchSchedulerResult:
        started_at = now or datetime.now(UTC)
        if started_at.tzinfo is None:
            raise ValueError("now must be timezone-aware")
        rule = self.state_store.get_rule(rule_id)
        if rule is None:
            raise KeyError(f"Unknown watch rule: {rule_id}")
        if not rule.enabled:
            raise ValueError(f"Watch rule is disabled: {rule.name}")
        return await self._run_rules(
            (rule,),
            started_at=started_at,
            page_size=page_size,
            max_pages=max_pages,
        )

    async def _run_rules(
        self,
        rules: tuple[WatchRule, ...],
        *,
        started_at: datetime,
        page_size: int,
        max_pages: int,
    ) -> WatchSchedulerResult:
        runs = []
        failures = []

        for rule in rules:
            try:
                result = await self.engine.run_rule(
                    rule,
                    now=started_at,
                    page_size=page_size,
                    max_pages=max_pages,
                )
            except Exception as exc:
                completed = datetime.now(UTC)
                self.state_store.record_failure(
                    rule.rule_id,
                    started_at=started_at,
                    completed_at=completed,
                    error=str(exc),
                )
                failures.append(
                    WatchRunFailure(
                        rule_id=rule.rule_id,
                        error=str(exc),
                    )
                )
                continue
            runs.append(result)

        return WatchSchedulerResult(
            due_rule_ids=tuple(rule.rule_id for rule in rules),
            runs=tuple(runs),
            failures=tuple(failures),
            started_at=started_at,
            completed_at=datetime.now(UTC),
        )
