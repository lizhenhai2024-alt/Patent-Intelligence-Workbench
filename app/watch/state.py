"""SQLite persistence for Patent Watch rules, state and run history."""

from __future__ import annotations

import json
import sqlite3
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

from app.sqlite_connection import ThreadLocalSQLite
from app.watch.models import WatchRule, WatchRunResult


@dataclass(frozen=True, slots=True)
class WatchRuleState:
    rule_id: str
    baselined_at: datetime | None
    last_run_at: datetime | None


@dataclass(frozen=True, slots=True)
class WatchRunHistory:
    run_id: int
    rule_id: str
    status: str
    started_at: datetime
    completed_at: datetime
    baseline_created: bool
    searched_hits: int
    resolved_families: int
    event_count: int
    error_count: int
    fatal_error: str | None


class SQLiteWatchStateStore:
    def __init__(self, path: str | Path):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._connections = ThreadLocalSQLite(self.path)
        self._init_schema()

    @property
    def connection(self) -> sqlite3.Connection:
        return self._connections.get()

    def close(self) -> None:
        self._connections.close_all()

    def _init_schema(self) -> None:
        self.connection.executescript(
            """
            PRAGMA foreign_keys = ON;

            CREATE TABLE IF NOT EXISTS watch_rule (
                rule_id TEXT PRIMARY KEY,
                name TEXT NOT NULL,
                company_group TEXT NOT NULL,
                technology_terms_json TEXT NOT NULL,
                jurisdictions_json TEXT NOT NULL,
                enabled INTEGER NOT NULL,
                lookback_days INTEGER NOT NULL,
                notify_on_first_run INTEGER NOT NULL,
                cadence_hours INTEGER NOT NULL DEFAULT 24
            );

            CREATE TABLE IF NOT EXISTS watch_rule_state (
                rule_id TEXT PRIMARY KEY,
                baselined_at TEXT,
                last_run_at TEXT,
                FOREIGN KEY(rule_id) REFERENCES watch_rule(rule_id) ON DELETE CASCADE
            );

            CREATE TABLE IF NOT EXISTS watch_seen_family (
                rule_id TEXT NOT NULL,
                family_key TEXT NOT NULL,
                family_source_id TEXT,
                first_seen_at TEXT NOT NULL,
                last_seen_at TEXT NOT NULL,
                PRIMARY KEY(rule_id, family_key),
                FOREIGN KEY(rule_id) REFERENCES watch_rule(rule_id) ON DELETE CASCADE
            );

            CREATE TABLE IF NOT EXISTS watch_seen_publication (
                rule_id TEXT NOT NULL,
                publication_number TEXT NOT NULL,
                family_key TEXT,
                first_seen_at TEXT NOT NULL,
                last_seen_at TEXT NOT NULL,
                PRIMARY KEY(rule_id, publication_number),
                FOREIGN KEY(rule_id) REFERENCES watch_rule(rule_id) ON DELETE CASCADE
            );

            CREATE TABLE IF NOT EXISTS watch_run_history (
                run_id INTEGER PRIMARY KEY AUTOINCREMENT,
                rule_id TEXT NOT NULL,
                status TEXT NOT NULL,
                started_at TEXT NOT NULL,
                completed_at TEXT NOT NULL,
                baseline_created INTEGER NOT NULL DEFAULT 0,
                searched_hits INTEGER NOT NULL DEFAULT 0,
                resolved_families INTEGER NOT NULL DEFAULT 0,
                event_count INTEGER NOT NULL DEFAULT 0,
                error_count INTEGER NOT NULL DEFAULT 0,
                fatal_error TEXT,
                FOREIGN KEY(rule_id) REFERENCES watch_rule(rule_id) ON DELETE CASCADE
            );
            """
        )
        self._ensure_column(
            "watch_rule",
            "cadence_hours",
            "INTEGER NOT NULL DEFAULT 24",
        )
        self.connection.commit()

    def _ensure_column(
        self,
        table: str,
        column: str,
        definition: str,
    ) -> None:
        columns = {
            row["name"]
            for row in self.connection.execute(f"PRAGMA table_info({table})").fetchall()
        }
        if column not in columns:
            self.connection.execute(
                f"ALTER TABLE {table} ADD COLUMN {column} {definition}"
            )

    def upsert_rule(self, rule: WatchRule) -> None:
        self.connection.execute(
            """
            INSERT INTO watch_rule (
                rule_id, name, company_group, technology_terms_json,
                jurisdictions_json, enabled, lookback_days, notify_on_first_run,
                cadence_hours
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(rule_id) DO UPDATE SET
                name=excluded.name,
                company_group=excluded.company_group,
                technology_terms_json=excluded.technology_terms_json,
                jurisdictions_json=excluded.jurisdictions_json,
                enabled=excluded.enabled,
                lookback_days=excluded.lookback_days,
                notify_on_first_run=excluded.notify_on_first_run,
                cadence_hours=excluded.cadence_hours
            """,
            (
                rule.rule_id,
                rule.name,
                rule.company_group,
                json.dumps(rule.technology_terms, ensure_ascii=False),
                json.dumps(rule.jurisdictions, ensure_ascii=False),
                int(rule.enabled),
                rule.lookback_days,
                int(rule.notify_on_first_run),
                rule.cadence_hours,
            ),
        )
        self.connection.execute(
            "INSERT OR IGNORE INTO watch_rule_state(rule_id) VALUES (?)",
            (rule.rule_id,),
        )
        self.connection.commit()

    def get_rule(self, rule_id: str) -> WatchRule | None:
        row = self.connection.execute(
            "SELECT * FROM watch_rule WHERE rule_id = ?",
            (rule_id,),
        ).fetchone()
        if row is None:
            return None
        return WatchRule(
            rule_id=row["rule_id"],
            name=row["name"],
            company_group=row["company_group"],
            technology_terms=tuple(json.loads(row["technology_terms_json"])),
            jurisdictions=tuple(json.loads(row["jurisdictions_json"])),
            enabled=bool(row["enabled"]),
            lookback_days=int(row["lookback_days"]),
            notify_on_first_run=bool(row["notify_on_first_run"]),
            cadence_hours=int(row["cadence_hours"]),
        )

    def list_rules(self) -> tuple[WatchRule, ...]:
        rows = self.connection.execute(
            "SELECT rule_id FROM watch_rule ORDER BY name, rule_id"
        ).fetchall()
        return tuple(
            rule
            for row in rows
            if (rule := self.get_rule(row["rule_id"])) is not None
        )

    def get_state(self, rule_id: str) -> WatchRuleState:
        row = self.connection.execute(
            "SELECT * FROM watch_rule_state WHERE rule_id = ?",
            (rule_id,),
        ).fetchone()
        if row is None:
            return WatchRuleState(rule_id, None, None)
        return WatchRuleState(
            rule_id=rule_id,
            baselined_at=_parse_datetime(row["baselined_at"]),
            last_run_at=_parse_datetime(row["last_run_at"]),
        )

    def mark_baselined(self, rule_id: str, at: datetime) -> None:
        self.connection.execute(
            """
            UPDATE watch_rule_state
            SET baselined_at = COALESCE(baselined_at, ?)
            WHERE rule_id = ?
            """,
            (_format_datetime(at), rule_id),
        )
        self.connection.commit()

    def mark_run(self, rule_id: str, at: datetime) -> None:
        self.connection.execute(
            "UPDATE watch_rule_state SET last_run_at = ? WHERE rule_id = ?",
            (_format_datetime(at), rule_id),
        )
        self.connection.commit()

    def publication_family_key(
        self,
        rule_id: str,
        publication_number: str,
    ) -> str | None:
        row = self.connection.execute(
            """
            SELECT family_key FROM watch_seen_publication
            WHERE rule_id = ? AND publication_number = ?
            """,
            (rule_id, publication_number),
        ).fetchone()
        if row is None:
            return None
        return row["family_key"]

    def publication_seen(self, rule_id: str, publication_number: str) -> bool:
        row = self.connection.execute(
            """
            SELECT 1 FROM watch_seen_publication
            WHERE rule_id = ? AND publication_number = ?
            """,
            (rule_id, publication_number),
        ).fetchone()
        return row is not None

    def family_seen(self, rule_id: str, family_key: str) -> bool:
        row = self.connection.execute(
            """
            SELECT 1 FROM watch_seen_family
            WHERE rule_id = ? AND family_key = ?
            """,
            (rule_id, family_key),
        ).fetchone()
        return row is not None

    def family_members(self, rule_id: str, family_key: str) -> frozenset[str]:
        rows = self.connection.execute(
            """
            SELECT publication_number FROM watch_seen_publication
            WHERE rule_id = ? AND family_key = ?
            """,
            (rule_id, family_key),
        ).fetchall()
        return frozenset(row["publication_number"] for row in rows)

    def mark_family(
        self,
        rule_id: str,
        family_key: str,
        *,
        family_source_id: str | None,
        at: datetime,
    ) -> None:
        stamp = _format_datetime(at)
        self.connection.execute(
            """
            INSERT INTO watch_seen_family (
                rule_id, family_key, family_source_id, first_seen_at, last_seen_at
            ) VALUES (?, ?, ?, ?, ?)
            ON CONFLICT(rule_id, family_key) DO UPDATE SET
                family_source_id=COALESCE(excluded.family_source_id, family_source_id),
                last_seen_at=excluded.last_seen_at
            """,
            (rule_id, family_key, family_source_id, stamp, stamp),
        )

    def mark_publication(
        self,
        rule_id: str,
        publication_number: str,
        *,
        family_key: str | None,
        at: datetime,
    ) -> None:
        stamp = _format_datetime(at)
        self.connection.execute(
            """
            INSERT INTO watch_seen_publication (
                rule_id, publication_number, family_key, first_seen_at, last_seen_at
            ) VALUES (?, ?, ?, ?, ?)
            ON CONFLICT(rule_id, publication_number) DO UPDATE SET
                family_key=COALESCE(excluded.family_key, family_key),
                last_seen_at=excluded.last_seen_at
            """,
            (rule_id, publication_number, family_key, stamp, stamp),
        )

    def record_run(self, result: WatchRunResult) -> None:
        self.connection.execute(
            """
            INSERT INTO watch_run_history (
                rule_id, status, started_at, completed_at, baseline_created,
                searched_hits, resolved_families, event_count, error_count, fatal_error
            ) VALUES (?, 'success', ?, ?, ?, ?, ?, ?, ?, NULL)
            """,
            (
                result.rule_id,
                _format_datetime(result.started_at),
                _format_datetime(result.completed_at),
                int(result.baseline_created),
                result.searched_hits,
                result.resolved_families,
                len(result.events),
                len(result.errors),
            ),
        )
        self.connection.commit()

    def record_failure(
        self,
        rule_id: str,
        *,
        started_at: datetime,
        completed_at: datetime,
        error: str,
    ) -> None:
        self.connection.execute(
            """
            INSERT INTO watch_run_history (
                rule_id, status, started_at, completed_at, baseline_created,
                searched_hits, resolved_families, event_count, error_count, fatal_error
            ) VALUES (?, 'failure', ?, ?, 0, 0, 0, 0, 1, ?)
            """,
            (
                rule_id,
                _format_datetime(started_at),
                _format_datetime(completed_at),
                error,
            ),
        )
        self.connection.commit()

    def last_attempt_at(self, rule_id: str) -> datetime | None:
        row = self.connection.execute(
            """
            SELECT completed_at
            FROM watch_run_history
            WHERE rule_id = ?
            ORDER BY run_id DESC
            LIMIT 1
            """,
            (rule_id,),
        ).fetchone()
        if row is None:
            return None
        return _parse_datetime(row["completed_at"])

    def recent_runs(self, limit: int = 50) -> tuple[WatchRunHistory, ...]:
        if limit < 1:
            raise ValueError("limit must be >= 1")
        rows = self.connection.execute(
            """
            SELECT * FROM watch_run_history
            ORDER BY run_id DESC
            LIMIT ?
            """,
            (limit,),
        ).fetchall()
        return tuple(
            WatchRunHistory(
                run_id=int(row["run_id"]),
                rule_id=row["rule_id"],
                status=row["status"],
                started_at=datetime.fromisoformat(row["started_at"]),
                completed_at=datetime.fromisoformat(row["completed_at"]),
                baseline_created=bool(row["baseline_created"]),
                searched_hits=int(row["searched_hits"]),
                resolved_families=int(row["resolved_families"]),
                event_count=int(row["event_count"]),
                error_count=int(row["error_count"]),
                fatal_error=row["fatal_error"],
            )
            for row in rows
        )

    def commit(self) -> None:
        self.connection.commit()


def _format_datetime(value: datetime) -> str:
    return value.isoformat()


def _parse_datetime(value: str | None) -> datetime | None:
    return datetime.fromisoformat(value) if value else None
