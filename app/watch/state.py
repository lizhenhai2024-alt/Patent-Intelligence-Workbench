"""SQLite persistence for Patent Watch rules and seen-family state."""

from __future__ import annotations

import json
import sqlite3
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

from app.watch.models import WatchRule


@dataclass(frozen=True, slots=True)
class WatchRuleState:
    rule_id: str
    baselined_at: datetime | None
    last_run_at: datetime | None


class SQLiteWatchStateStore:
    def __init__(self, path: str | Path):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.connection = sqlite3.connect(self.path)
        self.connection.row_factory = sqlite3.Row
        self._init_schema()

    def close(self) -> None:
        self.connection.close()

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
                notify_on_first_run INTEGER NOT NULL
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
            """
        )
        self.connection.commit()

    def upsert_rule(self, rule: WatchRule) -> None:
        self.connection.execute(
            """
            INSERT INTO watch_rule (
                rule_id, name, company_group, technology_terms_json,
                jurisdictions_json, enabled, lookback_days, notify_on_first_run
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(rule_id) DO UPDATE SET
                name=excluded.name,
                company_group=excluded.company_group,
                technology_terms_json=excluded.technology_terms_json,
                jurisdictions_json=excluded.jurisdictions_json,
                enabled=excluded.enabled,
                lookback_days=excluded.lookback_days,
                notify_on_first_run=excluded.notify_on_first_run
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

    def commit(self) -> None:
        self.connection.commit()


def _format_datetime(value: datetime) -> str:
    return value.isoformat()


def _parse_datetime(value: str | None) -> datetime | None:
    return datetime.fromisoformat(value) if value else None
