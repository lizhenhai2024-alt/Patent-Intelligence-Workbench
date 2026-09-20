"""SQLite-backed local patent library."""

from __future__ import annotations

import json
import sqlite3
from collections.abc import Iterable
from datetime import UTC, date, datetime
from pathlib import Path

from app.domain.family import PatentFamily, PatentPublication
from app.library.models import LibraryFamilySummary, LibraryPatent, LibraryQuery
from app.watch.family_key import derive_family_key


class SQLitePatentLibrary:
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

            CREATE TABLE IF NOT EXISTS library_family (
                family_key TEXT PRIMARY KEY,
                family_type TEXT NOT NULL,
                source TEXT NOT NULL,
                source_family_id TEXT,
                earliest_priority_number TEXT,
                earliest_priority_date TEXT,
                first_seen_at TEXT NOT NULL,
                last_seen_at TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS library_publication (
                publication_number TEXT PRIMARY KEY,
                jurisdiction TEXT NOT NULL,
                kind_code TEXT,
                family_key TEXT,
                application_number TEXT,
                grant_number TEXT,
                title TEXT,
                publication_date TEXT,
                original_assignees_json TEXT NOT NULL DEFAULT '[]',
                current_assignees_json TEXT NOT NULL DEFAULT '[]',
                source TEXT,
                favorite INTEGER NOT NULL DEFAULT 0,
                note TEXT,
                first_seen_at TEXT NOT NULL,
                last_seen_at TEXT NOT NULL,
                FOREIGN KEY(family_key) REFERENCES library_family(family_key)
                    ON DELETE SET NULL
            );

            CREATE TABLE IF NOT EXISTS library_pdf (
                publication_number TEXT NOT NULL,
                path TEXT NOT NULL,
                provider TEXT,
                source_url TEXT,
                added_at TEXT NOT NULL,
                PRIMARY KEY(publication_number, path),
                FOREIGN KEY(publication_number)
                    REFERENCES library_publication(publication_number)
                    ON DELETE CASCADE
            );

            CREATE TABLE IF NOT EXISTS library_company_group (
                publication_number TEXT NOT NULL,
                company_group TEXT NOT NULL,
                PRIMARY KEY(publication_number, company_group),
                FOREIGN KEY(publication_number)
                    REFERENCES library_publication(publication_number)
                    ON DELETE CASCADE
            );

            CREATE TABLE IF NOT EXISTS library_technology_topic (
                publication_number TEXT NOT NULL,
                topic TEXT NOT NULL,
                PRIMARY KEY(publication_number, topic),
                FOREIGN KEY(publication_number)
                    REFERENCES library_publication(publication_number)
                    ON DELETE CASCADE
            );

            CREATE TABLE IF NOT EXISTS library_project (
                publication_number TEXT NOT NULL,
                project TEXT NOT NULL,
                PRIMARY KEY(publication_number, project),
                FOREIGN KEY(publication_number)
                    REFERENCES library_publication(publication_number)
                    ON DELETE CASCADE
            );

            CREATE TABLE IF NOT EXISTS library_tag (
                publication_number TEXT NOT NULL,
                tag TEXT NOT NULL,
                PRIMARY KEY(publication_number, tag),
                FOREIGN KEY(publication_number)
                    REFERENCES library_publication(publication_number)
                    ON DELETE CASCADE
            );

            CREATE TABLE IF NOT EXISTS library_watch_source (
                publication_number TEXT NOT NULL,
                rule_id TEXT NOT NULL,
                event_type TEXT,
                detected_at TEXT,
                PRIMARY KEY(publication_number, rule_id),
                FOREIGN KEY(publication_number)
                    REFERENCES library_publication(publication_number)
                    ON DELETE CASCADE
            );

            CREATE INDEX IF NOT EXISTS idx_library_publication_family
                ON library_publication(family_key);
            CREATE INDEX IF NOT EXISTS idx_library_publication_jurisdiction
                ON library_publication(jurisdiction);
            CREATE INDEX IF NOT EXISTS idx_library_company_group
                ON library_company_group(company_group);
            CREATE INDEX IF NOT EXISTS idx_library_technology_topic
                ON library_technology_topic(topic);
            CREATE INDEX IF NOT EXISTS idx_library_project
                ON library_project(project);
            CREATE INDEX IF NOT EXISTS idx_library_tag
                ON library_tag(tag);
            """
        )
        self.connection.commit()

    def upsert_family(
        self,
        family: PatentFamily,
        *,
        seen_at: datetime | None = None,
        source_override: str | None = None,
    ) -> str:
        stamp = _aware_or_now(seen_at)
        family_key = derive_family_key(family)
        earliest = family.earliest_priority
        source = source_override or family.source

        self.connection.execute(
            """
            INSERT INTO library_family (
                family_key, family_type, source, source_family_id,
                earliest_priority_number, earliest_priority_date,
                first_seen_at, last_seen_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(family_key) DO UPDATE SET
                family_type=excluded.family_type,
                source=excluded.source,
                source_family_id=COALESCE(excluded.source_family_id, source_family_id),
                earliest_priority_number=COALESCE(
                    excluded.earliest_priority_number,
                    earliest_priority_number
                ),
                earliest_priority_date=COALESCE(
                    excluded.earliest_priority_date,
                    earliest_priority_date
                ),
                last_seen_at=excluded.last_seen_at
            """,
            (
                family_key,
                family.family_type.value,
                source,
                family.source_family_id,
                earliest.number if earliest else None,
                earliest.priority_date.isoformat()
                if earliest and earliest.priority_date
                else None,
                stamp.isoformat(),
                stamp.isoformat(),
            ),
        )

        for member in family.members:
            self.upsert_publication(
                member,
                family_key=family_key,
                source=source,
                seen_at=stamp,
                commit=False,
            )
        self.connection.commit()
        return family_key

    def upsert_publication(
        self,
        publication: PatentPublication,
        *,
        family_key: str | None = None,
        source: str | None = None,
        seen_at: datetime | None = None,
        commit: bool = True,
    ) -> None:
        stamp = _aware_or_now(seen_at)
        self.connection.execute(
            """
            INSERT INTO library_publication (
                publication_number, jurisdiction, kind_code, family_key,
                application_number, grant_number, title, publication_date,
                original_assignees_json, current_assignees_json, source,
                first_seen_at, last_seen_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(publication_number) DO UPDATE SET
                jurisdiction=excluded.jurisdiction,
                kind_code=COALESCE(excluded.kind_code, kind_code),
                family_key=COALESCE(excluded.family_key, family_key),
                application_number=COALESCE(
                    excluded.application_number,
                    application_number
                ),
                grant_number=COALESCE(excluded.grant_number, grant_number),
                title=COALESCE(excluded.title, title),
                publication_date=COALESCE(
                    excluded.publication_date,
                    publication_date
                ),
                original_assignees_json=CASE
                    WHEN excluded.original_assignees_json != '[]'
                    THEN excluded.original_assignees_json
                    ELSE original_assignees_json
                END,
                current_assignees_json=CASE
                    WHEN excluded.current_assignees_json != '[]'
                    THEN excluded.current_assignees_json
                    ELSE current_assignees_json
                END,
                source=COALESCE(excluded.source, source),
                last_seen_at=excluded.last_seen_at
            """,
            (
                publication.publication_number,
                publication.jurisdiction,
                publication.kind_code,
                family_key,
                publication.application_number,
                publication.grant_number,
                publication.title,
                publication.publication_date.isoformat()
                if publication.publication_date
                else None,
                json.dumps(publication.original_assignees, ensure_ascii=False),
                json.dumps(publication.current_assignees, ensure_ascii=False),
                source,
                stamp.isoformat(),
                stamp.isoformat(),
            ),
        )
        if commit:
            self.connection.commit()

    def attach_pdf(
        self,
        publication_number: str,
        path: str | Path,
        *,
        provider: str | None = None,
        source_url: str | None = None,
        added_at: datetime | None = None,
    ) -> None:
        self._require_publication(publication_number)
        stamp = _aware_or_now(added_at)
        normalized_path = str(Path(path))
        self.connection.execute(
            """
            INSERT INTO library_pdf (
                publication_number, path, provider, source_url, added_at
            ) VALUES (?, ?, ?, ?, ?)
            ON CONFLICT(publication_number, path) DO UPDATE SET
                provider=COALESCE(excluded.provider, provider),
                source_url=COALESCE(excluded.source_url, source_url)
            """,
            (
                publication_number,
                normalized_path,
                provider,
                source_url,
                stamp.isoformat(),
            ),
        )
        self.connection.commit()

    def set_favorite(self, publication_number: str, favorite: bool) -> None:
        self._require_publication(publication_number)
        self.connection.execute(
            """
            UPDATE library_publication
            SET favorite = ?
            WHERE publication_number = ?
            """,
            (int(favorite), publication_number),
        )
        self.connection.commit()

    def set_note(self, publication_number: str, note: str | None) -> None:
        self._require_publication(publication_number)
        self.connection.execute(
            """
            UPDATE library_publication
            SET note = ?
            WHERE publication_number = ?
            """,
            (note, publication_number),
        )
        self.connection.commit()

    def add_company_group(self, publication_number: str, company_group: str) -> None:
        self._add_relation(
            "library_company_group",
            "company_group",
            publication_number,
            company_group,
        )

    def add_technology_topic(self, publication_number: str, topic: str) -> None:
        self._add_relation(
            "library_technology_topic",
            "topic",
            publication_number,
            topic,
        )

    def add_project(self, publication_number: str, project: str) -> None:
        self._add_relation(
            "library_project",
            "project",
            publication_number,
            project,
        )

    def replace_projects(
        self,
        publication_number: str,
        projects: Iterable[str],
    ) -> None:
        self._replace_relations(
            "library_project",
            "project",
            publication_number,
            projects,
        )

    def add_tag(self, publication_number: str, tag: str) -> None:
        self._add_relation(
            "library_tag",
            "tag",
            publication_number,
            tag,
        )

    def replace_tags(
        self,
        publication_number: str,
        tags: Iterable[str],
    ) -> None:
        self._replace_relations(
            "library_tag",
            "tag",
            publication_number,
            tags,
        )

    def add_watch_source(
        self,
        publication_number: str,
        rule_id: str,
        *,
        event_type: str | None = None,
        detected_at: datetime | None = None,
    ) -> None:
        self._require_publication(publication_number)
        stamp = _aware_or_now(detected_at)
        self.connection.execute(
            """
            INSERT INTO library_watch_source (
                publication_number, rule_id, event_type, detected_at
            ) VALUES (?, ?, ?, ?)
            ON CONFLICT(publication_number, rule_id) DO UPDATE SET
                event_type=COALESCE(excluded.event_type, event_type),
                detected_at=COALESCE(excluded.detected_at, detected_at)
            """,
            (
                publication_number,
                rule_id.strip(),
                event_type,
                stamp.isoformat(),
            ),
        )
        self.connection.commit()

    def get_patent(self, publication_number: str) -> LibraryPatent | None:
        row = self.connection.execute(
            """
            SELECT p.*, f.family_type, f.source AS family_source,
                   f.source_family_id, f.earliest_priority_number,
                   f.earliest_priority_date
            FROM library_publication p
            LEFT JOIN library_family f ON f.family_key = p.family_key
            WHERE p.publication_number = ?
            """,
            (publication_number,),
        ).fetchone()
        if row is None:
            return None
        return self._row_to_patent(row)

    def query(self, query: LibraryQuery | None = None) -> tuple[LibraryPatent, ...]:
        filters = query or LibraryQuery()
        if filters.limit < 1:
            raise ValueError("limit must be >= 1")

        clauses: list[str] = []
        params: list[object] = []

        if filters.text and filters.text.strip():
            needle = f"%{filters.text.strip()}%"
            clauses.append(
                """
                (
                    p.publication_number LIKE ?
                    OR COALESCE(p.title, '') LIKE ?
                    OR p.original_assignees_json LIKE ?
                    OR p.current_assignees_json LIKE ?
                    OR COALESCE(p.note, '') LIKE ?
                )
                """
            )
            params.extend([needle, needle, needle, needle, needle])

        if filters.jurisdictions:
            _append_in_filter(
                clauses,
                params,
                "p.jurisdiction",
                tuple(value.upper() for value in filters.jurisdictions),
            )

        if filters.favorite_only:
            clauses.append("p.favorite = 1")

        relation_filters = (
            ("library_company_group", "company_group", filters.company_groups),
            ("library_technology_topic", "topic", filters.technology_topics),
            ("library_project", "project", filters.projects),
            ("library_tag", "tag", filters.tags),
            ("library_watch_source", "rule_id", filters.watch_rule_ids),
        )
        for table, column, values in relation_filters:
            if not values:
                continue
            placeholders = ",".join("?" for _ in values)
            clauses.append(
                f"""
                EXISTS (
                    SELECT 1 FROM {table} r
                    WHERE r.publication_number = p.publication_number
                    AND r.{column} IN ({placeholders})
                )
                """
            )
            params.extend(values)

        where = "WHERE " + " AND ".join(clauses) if clauses else ""
        params.append(filters.limit)
        rows = self.connection.execute(
            f"""
            SELECT p.*, f.family_type, f.source AS family_source,
                   f.source_family_id, f.earliest_priority_number,
                   f.earliest_priority_date
            FROM library_publication p
            LEFT JOIN library_family f ON f.family_key = p.family_key
            {where}
            ORDER BY
                COALESCE(p.publication_date, '') DESC,
                p.publication_number
            LIMIT ?
            """,
            params,
        ).fetchall()
        return tuple(self._row_to_patent(row) for row in rows)

    def list_families(self, limit: int = 500) -> tuple[LibraryFamilySummary, ...]:
        if limit < 1:
            raise ValueError("limit must be >= 1")
        rows = self.connection.execute(
            """
            SELECT f.*, COUNT(p.publication_number) AS member_count
            FROM library_family f
            LEFT JOIN library_publication p ON p.family_key = f.family_key
            GROUP BY f.family_key
            ORDER BY f.last_seen_at DESC
            LIMIT ?
            """,
            (limit,),
        ).fetchall()
        return tuple(
            LibraryFamilySummary(
                family_key=row["family_key"],
                family_type=row["family_type"],
                source=row["source"],
                source_family_id=row["source_family_id"],
                earliest_priority_number=row["earliest_priority_number"],
                earliest_priority_date=_parse_date(row["earliest_priority_date"]),
                member_count=int(row["member_count"]),
                first_seen_at=datetime.fromisoformat(row["first_seen_at"]),
                last_seen_at=datetime.fromisoformat(row["last_seen_at"]),
            )
            for row in rows
        )

    def _row_to_patent(self, row: sqlite3.Row) -> LibraryPatent:
        publication_number = row["publication_number"]
        return LibraryPatent(
            publication_number=publication_number,
            jurisdiction=row["jurisdiction"],
            kind_code=row["kind_code"],
            family_key=row["family_key"],
            family_type=row["family_type"],
            family_source=row["family_source"],
            source_family_id=row["source_family_id"],
            title=row["title"],
            application_number=row["application_number"],
            grant_number=row["grant_number"],
            publication_date=_parse_date(row["publication_date"]),
            earliest_priority_number=row["earliest_priority_number"],
            earliest_priority_date=_parse_date(row["earliest_priority_date"]),
            original_assignees=tuple(json.loads(row["original_assignees_json"])),
            current_assignees=tuple(json.loads(row["current_assignees_json"])),
            company_groups=self._relation_values(
                "library_company_group",
                "company_group",
                publication_number,
            ),
            technology_topics=self._relation_values(
                "library_technology_topic",
                "topic",
                publication_number,
            ),
            projects=self._relation_values(
                "library_project",
                "project",
                publication_number,
            ),
            tags=self._relation_values(
                "library_tag",
                "tag",
                publication_number,
            ),
            pdf_paths=tuple(
                Path(value)
                for value in self._relation_values(
                    "library_pdf",
                    "path",
                    publication_number,
                )
            ),
            watch_rule_ids=self._relation_values(
                "library_watch_source",
                "rule_id",
                publication_number,
            ),
            first_seen_at=datetime.fromisoformat(row["first_seen_at"]),
            last_seen_at=datetime.fromisoformat(row["last_seen_at"]),
            source=row["source"],
            favorite=bool(row["favorite"]),
            note=row["note"],
        )

    def _relation_values(
        self,
        table: str,
        column: str,
        publication_number: str,
    ) -> tuple[str, ...]:
        rows = self.connection.execute(
            f"""
            SELECT {column} FROM {table}
            WHERE publication_number = ?
            ORDER BY {column}
            """,
            (publication_number,),
        ).fetchall()
        return tuple(row[column] for row in rows)

    def _add_relation(
        self,
        table: str,
        column: str,
        publication_number: str,
        value: str,
    ) -> None:
        self._require_publication(publication_number)
        normalized = value.strip()
        if not normalized:
            raise ValueError(f"{column} must not be empty")
        self.connection.execute(
            f"""
            INSERT OR IGNORE INTO {table} (publication_number, {column})
            VALUES (?, ?)
            """,
            (publication_number, normalized),
        )
        self.connection.commit()

    def _replace_relations(
        self,
        table: str,
        column: str,
        publication_number: str,
        values: Iterable[str],
    ) -> None:
        self._require_publication(publication_number)
        normalized = tuple(
            dict.fromkeys(
                value.strip()
                for value in values
                if value.strip()
            )
        )
        with self.connection:
            self.connection.execute(
                f"DELETE FROM {table} WHERE publication_number = ?",
                (publication_number,),
            )
            self.connection.executemany(
                f"""
                INSERT INTO {table} (publication_number, {column})
                VALUES (?, ?)
                """,
                (
                    (publication_number, value)
                    for value in normalized
                ),
            )

    def _require_publication(self, publication_number: str) -> None:
        row = self.connection.execute(
            """
            SELECT 1 FROM library_publication WHERE publication_number = ?
            """,
            (publication_number,),
        ).fetchone()
        if row is None:
            raise KeyError(f"Unknown publication: {publication_number}")


def _aware_or_now(value: datetime | None) -> datetime:
    result = value or datetime.now(UTC)
    if result.tzinfo is None:
        raise ValueError("datetime must be timezone-aware")
    return result


def _parse_date(value: str | None) -> date | None:
    return date.fromisoformat(value) if value else None


def _append_in_filter(
    clauses: list[str],
    params: list[object],
    field: str,
    values: Iterable[str],
) -> None:
    items = tuple(values)
    if not items:
        return
    placeholders = ",".join("?" for _ in items)
    clauses.append(f"{field} IN ({placeholders})")
    params.extend(items)
