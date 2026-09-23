"""EPO OPS-based full-text backfill for publications already in LocalLibrary.

Scope (SPEC-library-backfill.md, "阶段 0"): only publication numbers already
present in the library whose local full text is missing or incomplete. No
search/discovery of new publications happens here — that is the later,
un-built "coverage check" phase of the same SPEC. Network calls only happen
inside `run_backfill`, and only after the desktop UI has the user confirm.
"""

from __future__ import annotations

import json
import sqlite3
import time
import uuid
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path

from app.core.patent_number import PatentNumberError, normalize_patent_number
from app.library import fulltext
from app.library.store import SQLitePatentLibrary
from app.providers.base import ProviderError
from app.providers.epo_ops import EpoOpsProvider

SOURCE_TYPE = "EPO_OPS"
DEFAULT_LIMIT = 200
HARD_LIMIT = 1000
DEFAULT_DELAY_SECONDS = 0.5

_CANDIDATE_STATUSES = (fulltext.STATUS_NEEDS_OCR, fulltext.STATUS_PARTIAL, fulltext.STATUS_FAILED)


@dataclass(slots=True)
class BackfillOutcome:
    publication_number: str
    result: str  # "filled" | "no_data" | "error"
    detail: str = ""


@dataclass(slots=True)
class BackfillSummary:
    task_id: str
    scanned: int = 0
    filled: int = 0
    no_data: int = 0
    errors: int = 0
    cancelled: bool = False
    outcomes: list[BackfillOutcome] = field(default_factory=list)


def candidates(connection: sqlite3.Connection) -> list[str]:
    """Publication numbers already in the library with missing/poor local text."""
    placeholders = ", ".join("?" for _ in _CANDIDATE_STATUSES)
    rows = connection.execute(
        f"""
        SELECT p.publication_number
        FROM library_publication p
        LEFT JOIN library_text_source t ON t.publication_number = p.publication_number
        WHERE t.publication_number IS NULL OR t.status IN ({placeholders})
        ORDER BY p.publication_number
        """,
        _CANDIDATE_STATUSES,
    ).fetchall()
    return [row[0] for row in rows]


def _segments_from_text(section: str, text: str) -> tuple[fulltext.Segment, ...]:
    text = text.strip()
    if not text:
        return ()
    offsets: list[tuple[int, int | None]] = [(0, None)]
    span = (0, len(text))
    if section == "claims":
        return tuple(fulltext._claim_segments(text, offsets, span))
    return tuple(fulltext._description_segments(text, offsets, span))


def parsed_from_epo_text(claims_text: str, description_text: str) -> fulltext.ParsedText:
    claims = _segments_from_text("claims", claims_text)
    description = _segments_from_text("description", description_text)
    if not claims and not description:
        return fulltext.ParsedText(
            fulltext.STATUS_FAILED, "EPO OPS 未返回权利要求或说明书文本", ()
        )
    missing = [
        name
        for name, segments in (("权利要求", claims), ("说明书", description))
        if sum(len(s.text) for s in segments) < fulltext.MIN_SECTION_CHARS
    ]
    status = fulltext.STATUS_PARTIAL if missing else fulltext.STATUS_OK
    detail = f"EPO OPS 未识别出：{'、'.join(missing)}" if missing else ""
    return fulltext.ParsedText(status, detail, (*claims, *description))


def run_backfill(
    store: SQLitePatentLibrary,
    provider: EpoOpsProvider,
    publication_numbers: list[str],
    *,
    fetch_section: Callable[[EpoOpsProvider, object, str], Awaitable[str]] | None = None,
    progress: Callable[[int, int, str], None] | None = None,
    should_cancel: Callable[[], bool] | None = None,
    delay_seconds: float = DEFAULT_DELAY_SECONDS,
    sleep: Callable[[float], None] = time.sleep,
    run_coroutine: Callable[[Awaitable[str]], str] | None = None,
) -> BackfillSummary:
    """Fetch EPO OPS full text for each publication number and index it.

    Runs synchronously (one publication at a time) so it can drive the same
    sqlite3.Connection the desktop app already owns from a single background
    thread. `run_coroutine` defaults to `asyncio.run`; tests can substitute a
    stub to avoid a real network call and a real event loop.
    """
    import asyncio

    if run_coroutine is None:
        run_coroutine = asyncio.run
    if fetch_section is None:

        async def fetch_section(provider: EpoOpsProvider, patent: object, section: str) -> str:
            return await provider.get_fulltext_section(patent, section)  # type: ignore[arg-type]

    task_id = f"backfill-{datetime.now(UTC).strftime('%Y%m%dT%H%M%S')}-{uuid.uuid4().hex[:6]}"
    summary = BackfillSummary(task_id=task_id)
    total = len(publication_numbers)
    connection = store.connection

    for position, number in enumerate(publication_numbers, 1):
        if should_cancel and should_cancel():
            summary.cancelled = True
            break
        summary.scanned += 1
        if progress:
            progress(position, total, number)
        try:
            patent = normalize_patent_number(number)
        except PatentNumberError as exc:
            summary.errors += 1
            summary.outcomes.append(BackfillOutcome(number, "error", f"公开号格式无法识别：{exc}"))
            continue
        try:
            claims_text = run_coroutine(fetch_section(provider, patent, "claims"))
            if delay_seconds:
                sleep(delay_seconds)
            description_text = run_coroutine(fetch_section(provider, patent, "description"))
            if delay_seconds:
                sleep(delay_seconds)
        except ProviderError as exc:
            summary.errors += 1
            summary.outcomes.append(BackfillOutcome(number, "error", f"EPO OPS 请求失败：{exc}"))
            continue
        if not claims_text and not description_text:
            summary.no_data += 1
            summary.outcomes.append(
                BackfillOutcome(number, "no_data", "EPO OPS 无权利要求/说明书全文")
            )
            continue
        parsed = parsed_from_epo_text(claims_text, description_text)
        fulltext.replace_text(
            connection,
            number,
            parsed,
            source_type=SOURCE_TYPE,
            source_ref=f"EPO_OPS:{patent.canonical}",
            pdf_sha256=None,
        )
        store.add_provenance(number, "BACKFILL", task_id, commit=False)
        connection.commit()
        summary.filled += 1
        summary.outcomes.append(BackfillOutcome(number, "filled", parsed.status))

    return summary


def write_task_log(log_dir: Path, summary: BackfillSummary, *, limit: int) -> Path:
    log_dir.mkdir(parents=True, exist_ok=True)
    path = log_dir / f"{summary.task_id}.json"
    payload = {
        "task_id": summary.task_id,
        "source": SOURCE_TYPE,
        "limit": limit,
        "scanned": summary.scanned,
        "filled": summary.filled,
        "no_data": summary.no_data,
        "errors": summary.errors,
        "cancelled": summary.cancelled,
        "finished_at": datetime.now(UTC).isoformat(timespec="seconds"),
        "outcomes": [
            {"publication_number": o.publication_number, "result": o.result, "detail": o.detail}
            for o in summary.outcomes
        ],
    }
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    return path
