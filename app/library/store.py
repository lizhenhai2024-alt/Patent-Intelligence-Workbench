"""SQLite-backed local patent library.

The schema is additive and can coexist with Patent Watch tables in the same
SQLite file. This lets new desktop installations use one workbench database
without coupling the two services at code level.
"""

from __future__ import annotations

import json
import sqlite3
from collections.abc import Iterable, Iterator, Sequence
from datetime import UTC, date, datetime
from pathlib import Path

from app.domain.family import PatentFamily, PatentPublication
from app.library.models import (
    EvidenceRecord,
    LibraryClassification,
    LibraryDocument,
    LibraryFamilySummary,
    LibraryPatent,
    LibraryPriority,
    LibraryQuery,
    LibrarySource,
)
from app.sqlite_connection import ThreadLocalSQLite
from app.watch.family_key import derive_family_key

# Relation tables that hang off a publication, as (table, value column) pairs.
# They are only ever read through `_row_to_patent`; batching them keeps the
# library grid from issuing one query per patent per relation.
_RELATION_COLUMNS: tuple[tuple[str, str], ...] = (
    ("library_company_group", "company_group"),
    ("library_technology_topic", "topic"),
    ("library_project", "project"),
    ("library_tag", "tag"),
    ("library_watch_source", "rule_id"),
)

# Stay well under SQLite's bound-parameter ceiling for IN (...) lists.
_BATCH_CHUNK = 400


def _chunked(values: Sequence[str], size: int = _BATCH_CHUNK) -> Iterator[tuple[str, ...]]:
    for index in range(0, len(values), size):
        yield tuple(values[index : index + size])


class SQLitePatentLibrary:
    def __init__(self, path: str | Path, *, read_only: bool = False):
        self.path = Path(path)
        self.read_only = read_only
        if read_only:
            # Read-only callers (e.g. agent tools) must never create or migrate a database.
            if not self.path.is_file():
                raise FileNotFoundError(f"LocalLibrary 数据库不存在：{self.path}")
            self._connections = ThreadLocalSQLite(self.path, read_only=True)
            return
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
                filing_date TEXT,
                publication_date TEXT,
                grant_date TEXT,
                language TEXT,
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

            CREATE TABLE IF NOT EXISTS library_priority_claim (
                publication_number TEXT NOT NULL,
                priority_number TEXT NOT NULL,
                country TEXT NOT NULL,
                priority_date TEXT,
                priority_type TEXT,
                PRIMARY KEY(publication_number, priority_number),
                FOREIGN KEY(publication_number)
                    REFERENCES library_publication(publication_number)
                    ON DELETE CASCADE
            );

            CREATE TABLE IF NOT EXISTS library_classification (
                publication_number TEXT NOT NULL,
                system TEXT NOT NULL,
                code TEXT NOT NULL,
                is_main INTEGER NOT NULL DEFAULT 0,
                PRIMARY KEY(publication_number, system, code),
                FOREIGN KEY(publication_number)
                    REFERENCES library_publication(publication_number)
                    ON DELETE CASCADE
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

            CREATE TABLE IF NOT EXISTS library_provenance (
                publication_number TEXT NOT NULL,
                source_type TEXT NOT NULL,
                source_ref TEXT NOT NULL,
                first_seen_at TEXT NOT NULL,
                last_seen_at TEXT NOT NULL,
                PRIMARY KEY(publication_number, source_type, source_ref),
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
            CREATE INDEX IF NOT EXISTS idx_library_provenance_type
                ON library_provenance(source_type);

            CREATE TABLE IF NOT EXISTS library_evidence (
                evidence_id TEXT PRIMARY KEY,
                source TEXT NOT NULL,
                source_type TEXT NOT NULL,
                title TEXT,
                markdown TEXT NOT NULL,
                metadata_json TEXT NOT NULL DEFAULT '{}',
                captured_at TEXT NOT NULL,
                publication_number TEXT,
                company_group TEXT,
                technology_topic TEXT,
                tags_json TEXT NOT NULL DEFAULT '[]',
                FOREIGN KEY(publication_number)
                    REFERENCES library_publication(publication_number)
                    ON DELETE SET NULL
            );

            CREATE INDEX IF NOT EXISTS idx_library_evidence_publication
                ON library_evidence(publication_number);
            CREATE INDEX IF NOT EXISTS idx_library_evidence_source_type
                ON library_evidence(source_type);
            """
        )
        self._ensure_column("library_publication", "filing_date", "TEXT")
        self._ensure_column("library_publication", "grant_date", "TEXT")
        self._ensure_column("library_publication", "language", "TEXT")
        from app.library.fulltext import ensure_fulltext_schema  # heavy import kept lazy

        self.fulltext_trigram = ensure_fulltext_schema(self.connection)
        self.connection.commit()

    def _ensure_column(
        self,
        table: str,
        column: str,
        definition: str,
    ) -> None:
        rows = self.connection.execute(f"PRAGMA table_info({table})").fetchall()
        columns = {row["name"] for row in rows}
        if column not in columns:
            self.connection.execute(f"ALTER TABLE {table} ADD COLUMN {column} {definition}")

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
                earliest.priority_date.isoformat() if earliest and earliest.priority_date else None,
                stamp.isoformat(),
                stamp.isoformat(),
            ),
        )

        family_ref = family.source_family_id or family_key
        for member in family.members:
            self.upsert_publication(
                member,
                family_key=family_key,
                source=source,
                seen_at=stamp,
                commit=False,
            )
            self.add_provenance(
                member.publication_number,
                "FAMILY",
                family_ref,
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
                application_number, grant_number, title, filing_date,
                publication_date, grant_date, language,
                original_assignees_json, current_assignees_json, source,
                first_seen_at, last_seen_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
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
                filing_date=COALESCE(excluded.filing_date, filing_date),
                publication_date=COALESCE(
                    excluded.publication_date,
                    publication_date
                ),
                grant_date=COALESCE(excluded.grant_date, grant_date),
                language=COALESCE(excluded.language, language),
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
                _date_to_text(publication.filing_date),
                _date_to_text(publication.publication_date),
                _date_to_text(publication.grant_date),
                publication.language,
                json.dumps(publication.original_assignees, ensure_ascii=False),
                json.dumps(publication.current_assignees, ensure_ascii=False),
                source,
                stamp.isoformat(),
                stamp.isoformat(),
            ),
        )
        self._replace_priority_claims(publication)
        self._replace_classifications(publication)
        if source:
            self.add_provenance(
                publication.publication_number,
                "PROVIDER",
                source,
                seen_at=stamp,
                commit=False,
            )
        if commit:
            self.connection.commit()

    def add_provenance(
        self,
        publication_number: str,
        source_type: str,
        source_ref: str,
        *,
        seen_at: datetime | None = None,
        commit: bool = True,
    ) -> None:
        self._require_publication(publication_number)
        normalized_type = source_type.strip().upper()
        normalized_ref = source_ref.strip()
        if not normalized_type or not normalized_ref:
            raise ValueError("source_type and source_ref must not be empty")
        stamp = _aware_or_now(seen_at).isoformat()
        self.connection.execute(
            """
            INSERT INTO library_provenance (
                publication_number, source_type, source_ref,
                first_seen_at, last_seen_at
            ) VALUES (?, ?, ?, ?, ?)
            ON CONFLICT(publication_number, source_type, source_ref) DO UPDATE SET
                last_seen_at=excluded.last_seen_at
            """,
            (
                publication_number,
                normalized_type,
                normalized_ref,
                stamp,
                stamp,
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
                source_url=COALESCE(excluded.source_url, source_url),
                added_at=excluded.added_at
            """,
            (
                publication_number,
                normalized_path,
                provider,
                source_url,
                stamp.isoformat(),
            ),
        )
        self.add_provenance(
            publication_number,
            "DOWNLOAD",
            provider or source_url or normalized_path,
            seen_at=stamp,
            commit=False,
        )
        self.connection.commit()

    def set_favorite(self, publication_number: str, favorite: bool) -> None:
        self._require_publication(publication_number)
        self.connection.execute(
            "UPDATE library_publication SET favorite = ? WHERE publication_number = ?",
            (int(favorite), publication_number),
        )
        self.connection.commit()

    def set_note(self, publication_number: str, note: str | None) -> None:
        self._require_publication(publication_number)
        self.connection.execute(
            "UPDATE library_publication SET note = ? WHERE publication_number = ?",
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
        normalized_rule = rule_id.strip()
        if not normalized_rule:
            raise ValueError("rule_id must not be empty")
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
                normalized_rule,
                event_type,
                stamp.isoformat(),
            ),
        )
        self.add_provenance(
            publication_number,
            "WATCH",
            normalized_rule,
            seen_at=stamp,
            commit=False,
        )
        self.connection.commit()

    def add_evidence(self, record: EvidenceRecord) -> None:
        publication = record.publication_number
        if publication:
            self._require_publication(publication)
        self.connection.execute(
            """
            INSERT INTO library_evidence (
                evidence_id, source, source_type, title, markdown,
                metadata_json, captured_at, publication_number,
                company_group, technology_topic, tags_json
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(evidence_id) DO UPDATE SET
                source=excluded.source,
                source_type=excluded.source_type,
                title=excluded.title,
                markdown=excluded.markdown,
                metadata_json=excluded.metadata_json,
                captured_at=excluded.captured_at,
                publication_number=excluded.publication_number,
                company_group=excluded.company_group,
                technology_topic=excluded.technology_topic,
                tags_json=excluded.tags_json
            """,
            (
                record.evidence_id,
                record.source,
                record.source_type,
                record.title,
                record.markdown,
                record.metadata_json,
                record.captured_at.isoformat(),
                publication,
                record.company_group,
                record.technology_topic,
                json.dumps(record.tags, ensure_ascii=False),
            ),
        )
        if publication:
            self.add_provenance(
                publication,
                "EVIDENCE",
                record.source,
                seen_at=record.captured_at,
                commit=False,
            )
        self.connection.commit()

    def list_evidence(
        self,
        *,
        publication_number: str | None = None,
        text: str | None = None,
        source_type: str | None = None,
        company_group: str | None = None,
        technology_topic: str | None = None,
        limit: int = 200,
    ) -> tuple[EvidenceRecord, ...]:
        clauses: list[str] = []
        params: list[object] = []
        if publication_number:
            clauses.append("publication_number = ?")
            params.append(publication_number)
        if text and text.strip():
            needle = f"%{text.strip()}%"
            clauses.append("(source LIKE ? OR title LIKE ? OR markdown LIKE ?)")
            params.extend((needle, needle, needle))
        if source_type and source_type.strip():
            clauses.append("source_type = ?")
            params.append(source_type.strip())
        if company_group and company_group.strip():
            clauses.append("company_group = ?")
            params.append(company_group.strip())
        if technology_topic and technology_topic.strip():
            clauses.append("technology_topic = ?")
            params.append(technology_topic.strip())
        sql = "SELECT * FROM library_evidence"
        if clauses:
            sql += " WHERE " + " AND ".join(clauses)
        sql += " ORDER BY captured_at DESC LIMIT ?"
        params.append(limit)
        rows = self.connection.execute(sql, params).fetchall()
        return tuple(
            EvidenceRecord(
                evidence_id=row["evidence_id"],
                source=row["source"],
                source_type=row["source_type"],
                title=row["title"],
                markdown=row["markdown"],
                metadata_json=row["metadata_json"],
                captured_at=datetime.fromisoformat(row["captured_at"]),
                publication_number=row["publication_number"],
                company_group=row["company_group"],
                technology_topic=row["technology_topic"],
                tags=tuple(json.loads(row["tags_json"] or "[]")),
            )
            for row in rows
        )

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
                    OR EXISTS (
                        SELECT 1 FROM library_classification c
                        WHERE c.publication_number = p.publication_number
                        AND c.code LIKE ?
                    )
                )
                """
            )
            params.extend([needle, needle, needle, needle, needle, needle])

        if filters.jurisdictions:
            _append_in_filter(
                clauses,
                params,
                "p.jurisdiction",
                tuple(value.upper() for value in filters.jurisdictions),
            )

        if filters.favorite_only:
            clauses.append("p.favorite = 1")

        if filters.has_pdf is True:
            clauses.append(
                """
                EXISTS (
                    SELECT 1 FROM library_pdf d
                    WHERE d.publication_number = p.publication_number
                )
                """
            )
        elif filters.has_pdf is False:
            clauses.append(
                """
                NOT EXISTS (
                    SELECT 1 FROM library_pdf d
                    WHERE d.publication_number = p.publication_number
                )
                """
            )

        relation_filters = (
            ("library_company_group", "company_group", filters.company_groups),
            ("library_technology_topic", "topic", filters.technology_topics),
            ("library_project", "project", filters.projects),
            ("library_tag", "tag", filters.tags),
            ("library_watch_source", "rule_id", filters.watch_rule_ids),
            ("library_provenance", "source_type", filters.source_types),
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
        return self._batched_patents(rows)

    def get_family_members(self, family_key: str) -> tuple[LibraryPatent, ...]:
        rows = self.connection.execute(
            """
            SELECT p.*, f.family_type, f.source AS family_source,
                   f.source_family_id, f.earliest_priority_number,
                   f.earliest_priority_date
            FROM library_publication p
            LEFT JOIN library_family f ON f.family_key = p.family_key
            WHERE p.family_key = ?
            ORDER BY
                COALESCE(p.publication_date, '') ASC,
                p.publication_number
            """,
            (family_key,),
        ).fetchall()
        return self._batched_patents(rows)

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

    def count_patents(self) -> int:
        row = self.connection.execute(
            "SELECT COUNT(*) AS count FROM library_publication"
        ).fetchone()
        return int(row["count"])

    def count_families(self) -> int:
        row = self.connection.execute(
            "SELECT COUNT(*) AS count FROM library_family"
        ).fetchone()
        return int(row["count"])

    def count_evidence(self) -> int:
        row = self.connection.execute(
            "SELECT COUNT(*) AS count FROM library_evidence"
        ).fetchone()
        return int(row["count"])

    def _row_to_patent(self, row: sqlite3.Row) -> LibraryPatent:
        publication_number = row["publication_number"]
        # Resolve the PDF rows once; `pdf_paths` and `documents` describe the
        # same rows and previously triggered two identical queries.
        documents = self._documents(publication_number)
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
            pdf_paths=tuple(document.path for document in documents),
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
            filing_date=_parse_date(row["filing_date"]),
            grant_date=_parse_date(row["grant_date"]),
            language=row["language"],
            classifications=self._classifications(publication_number),
            priorities=self._priorities(publication_number),
            documents=documents,
            provenance=self._provenance(publication_number),
        )

    def _batched_patents(
        self,
        rows: Sequence[sqlite3.Row],
    ) -> tuple[LibraryPatent, ...]:
        """Build many `LibraryPatent` objects with a constant number of queries.

        `_row_to_patent` issues ~10 statements per patent. For the library grid
        (limit 1000) that meant thousands of round trips on the Tk main thread,
        so relations are loaded per chunk and grouped by publication number.
        Row ordering inside each group matches the single-row queries exactly.
        """
        if not rows:
            return ()
        numbers = tuple(row["publication_number"] for row in rows)

        relations: dict[tuple[str, str], dict[str, list[str]]] = {
            key: {} for key in _RELATION_COLUMNS
        }
        documents: dict[str, list[LibraryDocument]] = {}
        classifications: dict[str, list[LibraryClassification]] = {}
        priorities: dict[str, list[LibraryPriority]] = {}
        provenance: dict[str, list[LibrarySource]] = {}

        for chunk in _chunked(numbers):
            placeholders = ",".join("?" * len(chunk))
            for table, column in _RELATION_COLUMNS:
                bucket = relations[(table, column)]
                for row in self.connection.execute(
                    f"""
                    SELECT publication_number, {column} FROM {table}
                    WHERE publication_number IN ({placeholders})
                    ORDER BY publication_number, {column}
                    """,
                    chunk,
                ):
                    bucket.setdefault(row["publication_number"], []).append(row[column])

            for row in self.connection.execute(
                f"""
                SELECT publication_number, path, provider, source_url, added_at
                FROM library_pdf
                WHERE publication_number IN ({placeholders})
                ORDER BY publication_number, added_at DESC, path
                """,
                chunk,
            ):
                documents.setdefault(row["publication_number"], []).append(
                    LibraryDocument(
                        path=Path(row["path"]),
                        provider=row["provider"],
                        source_url=row["source_url"],
                        added_at=datetime.fromisoformat(row["added_at"]),
                    )
                )

            for row in self.connection.execute(
                f"""
                SELECT publication_number, system, code, is_main
                FROM library_classification
                WHERE publication_number IN ({placeholders})
                ORDER BY publication_number, system, is_main DESC, code
                """,
                chunk,
            ):
                classifications.setdefault(row["publication_number"], []).append(
                    LibraryClassification(
                        system=row["system"],
                        code=row["code"],
                        is_main=bool(row["is_main"]),
                    )
                )

            for row in self.connection.execute(
                f"""
                SELECT publication_number, priority_number, country,
                       priority_date, priority_type
                FROM library_priority_claim
                WHERE publication_number IN ({placeholders})
                ORDER BY publication_number, COALESCE(priority_date, ''),
                         priority_number
                """,
                chunk,
            ):
                priorities.setdefault(row["publication_number"], []).append(
                    LibraryPriority(
                        number=row["priority_number"],
                        country=row["country"],
                        priority_date=_parse_date(row["priority_date"]),
                        priority_type=row["priority_type"],
                    )
                )

            for row in self.connection.execute(
                f"""
                SELECT publication_number, source_type, source_ref,
                       first_seen_at, last_seen_at
                FROM library_provenance
                WHERE publication_number IN ({placeholders})
                ORDER BY publication_number, source_type, source_ref
                """,
                chunk,
            ):
                provenance.setdefault(row["publication_number"], []).append(
                    LibrarySource(
                        source_type=row["source_type"],
                        source_ref=row["source_ref"],
                        first_seen_at=datetime.fromisoformat(row["first_seen_at"]),
                        last_seen_at=datetime.fromisoformat(row["last_seen_at"]),
                    )
                )

        patents: list[LibraryPatent] = []
        for row in rows:
            number = row["publication_number"]
            patent_documents = tuple(documents.get(number, ()))
            patents.append(
                LibraryPatent(
                    publication_number=number,
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
                    company_groups=tuple(
                        relations[("library_company_group", "company_group")].get(number, ())
                    ),
                    technology_topics=tuple(
                        relations[("library_technology_topic", "topic")].get(number, ())
                    ),
                    projects=tuple(relations[("library_project", "project")].get(number, ())),
                    tags=tuple(relations[("library_tag", "tag")].get(number, ())),
                    pdf_paths=tuple(document.path for document in patent_documents),
                    watch_rule_ids=tuple(
                        relations[("library_watch_source", "rule_id")].get(number, ())
                    ),
                    first_seen_at=datetime.fromisoformat(row["first_seen_at"]),
                    last_seen_at=datetime.fromisoformat(row["last_seen_at"]),
                    source=row["source"],
                    favorite=bool(row["favorite"]),
                    note=row["note"],
                    filing_date=_parse_date(row["filing_date"]),
                    grant_date=_parse_date(row["grant_date"]),
                    language=row["language"],
                    classifications=tuple(classifications.get(number, ())),
                    priorities=tuple(priorities.get(number, ())),
                    documents=patent_documents,
                    provenance=tuple(provenance.get(number, ())),
                )
            )
        return tuple(patents)

    def _classifications(
        self,
        publication_number: str,
    ) -> tuple[LibraryClassification, ...]:
        rows = self.connection.execute(
            """
            SELECT system, code, is_main
            FROM library_classification
            WHERE publication_number = ?
            ORDER BY system, is_main DESC, code
            """,
            (publication_number,),
        ).fetchall()
        return tuple(
            LibraryClassification(
                system=row["system"],
                code=row["code"],
                is_main=bool(row["is_main"]),
            )
            for row in rows
        )

    def _priorities(
        self,
        publication_number: str,
    ) -> tuple[LibraryPriority, ...]:
        rows = self.connection.execute(
            """
            SELECT priority_number, country, priority_date, priority_type
            FROM library_priority_claim
            WHERE publication_number = ?
            ORDER BY COALESCE(priority_date, ''), priority_number
            """,
            (publication_number,),
        ).fetchall()
        return tuple(
            LibraryPriority(
                number=row["priority_number"],
                country=row["country"],
                priority_date=_parse_date(row["priority_date"]),
                priority_type=row["priority_type"],
            )
            for row in rows
        )

    def _documents(
        self,
        publication_number: str,
    ) -> tuple[LibraryDocument, ...]:
        rows = self.connection.execute(
            """
            SELECT path, provider, source_url, added_at
            FROM library_pdf
            WHERE publication_number = ?
            ORDER BY added_at DESC, path
            """,
            (publication_number,),
        ).fetchall()
        return tuple(
            LibraryDocument(
                path=Path(row["path"]),
                provider=row["provider"],
                source_url=row["source_url"],
                added_at=datetime.fromisoformat(row["added_at"]),
            )
            for row in rows
        )

    def _provenance(
        self,
        publication_number: str,
    ) -> tuple[LibrarySource, ...]:
        rows = self.connection.execute(
            """
            SELECT source_type, source_ref, first_seen_at, last_seen_at
            FROM library_provenance
            WHERE publication_number = ?
            ORDER BY source_type, source_ref
            """,
            (publication_number,),
        ).fetchall()
        return tuple(
            LibrarySource(
                source_type=row["source_type"],
                source_ref=row["source_ref"],
                first_seen_at=datetime.fromisoformat(row["first_seen_at"]),
                last_seen_at=datetime.fromisoformat(row["last_seen_at"]),
            )
            for row in rows
        )

    def _replace_priority_claims(self, publication: PatentPublication) -> None:
        if not publication.priorities:
            return
        self.connection.execute(
            "DELETE FROM library_priority_claim WHERE publication_number = ?",
            (publication.publication_number,),
        )
        self.connection.executemany(
            """
            INSERT INTO library_priority_claim (
                publication_number, priority_number, country,
                priority_date, priority_type
            ) VALUES (?, ?, ?, ?, ?)
            """,
            (
                (
                    publication.publication_number,
                    priority.number,
                    priority.country,
                    _date_to_text(priority.priority_date),
                    priority.priority_type,
                )
                for priority in publication.priorities
            ),
        )

    def _replace_classifications(self, publication: PatentPublication) -> None:
        if not publication.classifications:
            return
        self.connection.execute(
            "DELETE FROM library_classification WHERE publication_number = ?",
            (publication.publication_number,),
        )
        self.connection.executemany(
            """
            INSERT INTO library_classification (
                publication_number, system, code, is_main
            ) VALUES (?, ?, ?, ?)
            """,
            (
                (
                    publication.publication_number,
                    classification.system,
                    classification.code,
                    int(classification.is_main),
                )
                for classification in publication.classifications
            ),
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
        normalized = tuple(dict.fromkeys(value.strip() for value in values if value.strip()))
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
                ((publication_number, value) for value in normalized),
            )

    def _require_publication(self, publication_number: str) -> None:
        row = self.connection.execute(
            "SELECT 1 FROM library_publication WHERE publication_number = ?",
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


def _date_to_text(value: date | None) -> str | None:
    return value.isoformat() if value else None


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
