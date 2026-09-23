"""Local full-text index of patent PDFs (claims + description), SPEC-fulltext-index.

PDFs are parsed once into numbered segments with page numbers and indexed with
SQLite FTS5's trigram tokenizer, so Chinese terms of three or more characters
match anywhere in the text. Shorter terms fall back to LIKE.
"""

from __future__ import annotations

import hashlib
import re
import sqlite3
import unicodedata
from collections.abc import Callable, Iterable
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path

import pymupdf as fitz

from app.services.pdf_reader import _clean_pdf_text

STATUS_OK = "ok"
STATUS_PARTIAL = "partial"
STATUS_NEEDS_OCR = "needs_ocr"
STATUS_FAILED = "failed"
MIN_SECTION_CHARS = 200
MIN_CHARS_PER_PAGE = 20  # below this on average the PDF has no usable text layer
DESCRIPTION_CHUNK_CHARS = 800
SNIPPET_RADIUS = 60
MAX_SNIPPETS = 3

_SCHEMA = """
CREATE TABLE IF NOT EXISTS library_text_source (
    publication_number TEXT PRIMARY KEY,
    source_type TEXT NOT NULL,
    source_ref TEXT NOT NULL,
    pdf_sha256 TEXT,
    status TEXT NOT NULL,
    detail TEXT NOT NULL DEFAULT '',
    parsed_at TEXT NOT NULL,
    FOREIGN KEY(publication_number) REFERENCES library_publication(publication_number)
        ON DELETE CASCADE
);
CREATE TABLE IF NOT EXISTS library_text_segment (
    segment_id INTEGER PRIMARY KEY,
    publication_number TEXT NOT NULL,
    section TEXT NOT NULL,
    ordinal INTEGER NOT NULL,
    claim_number INTEGER,
    page_start INTEGER,
    page_end INTEGER,
    text TEXT NOT NULL,
    FOREIGN KEY(publication_number) REFERENCES library_publication(publication_number)
        ON DELETE CASCADE
);
CREATE INDEX IF NOT EXISTS idx_library_text_segment_publication
    ON library_text_segment(publication_number, section, ordinal);
"""
_FTS = "CREATE VIRTUAL TABLE IF NOT EXISTS library_text_fts USING fts5(text, tokenize='trigram')"

_CLAIM_RE = re.compile(r"(?m)^\s*(\d{1,3})\s*[.、．]\s*(?=\S)")
_PARAGRAPH_RE = re.compile(r"(?m)^\s*(?:\[\s*\d{3,5}\s*\]|【\s*\d{3,5}\s*】)")


@dataclass(frozen=True, slots=True)
class Segment:
    section: str  # claims | description
    ordinal: int
    text: str  # CJK line wraps already joined (see _unwrap)
    page_start: int | None = None
    page_end: int | None = None
    claim_number: int | None = None


@dataclass(frozen=True, slots=True)
class ParsedText:
    status: str
    detail: str
    segments: tuple[Segment, ...]


@dataclass(slots=True)
class IndexSummary:
    scanned: int = 0
    indexed: int = 0
    skipped: int = 0
    no_pdf: int = 0
    statuses: dict[str, int] = field(default_factory=dict)
    cancelled: bool = False


@dataclass(frozen=True, slots=True)
class Hit:
    publication_number: str
    matched_segments: int
    snippets: tuple[dict, ...]


# -- schema ----------------------------------------------------------------------


def ensure_fulltext_schema(connection: sqlite3.Connection) -> bool:
    """Create the full-text tables; returns False when FTS5 trigram is unavailable."""
    connection.executescript(_SCHEMA)
    try:
        connection.execute(_FTS)
    except sqlite3.OperationalError:
        return False
    return True


def tables_exist(connection: sqlite3.Connection) -> bool:
    row = connection.execute(
        "SELECT 1 FROM sqlite_master WHERE name = 'library_text_source'"
    ).fetchone()
    return row is not None


def has_fts(connection: sqlite3.Connection) -> bool:
    row = connection.execute(
        "SELECT 1 FROM sqlite_master WHERE name = 'library_text_fts'"
    ).fetchone()
    return row is not None


# -- parsing ---------------------------------------------------------------------


_H = r"(?m)^[ \t]*"  # heading at line start
# "权利要求书" is not listed: in CNIPA PDFs it is a running page header/footer, so the
# CN claims page is found by its first line "1." instead (see _locate).
_CLAIM_HEADINGS = (
    _H + r"Patentansprüche\s*$",
    r"(?i)(?:what\s+is\s+claimed(?:\s+is)?|the\s+invention\s+claimed\s+is|we\s+claim"
    r"|i\s+claim)\s*:",
    r"(?im)^[ \t]*claims\s*:?\s*$",
)
_JP_CLAIMS_HEADING = r"【特許請求の範囲】"  # may sit on page 1 of JP B publications
_US_FIRST_CLAIM = re.compile(r"(?m)^\s*1\s*\.\s*(?:An?|The|In)\s")
_DESCRIPTION_HEADINGS = (
    _H + r"【発明の詳細な説明】",
    _H + r"技\s*术\s*领\s*域\s*$",
    r"\[\s*0001\s*\]",
    r"【\s*0001\s*】",
    _H + r"Beschreibung\s*$",
    r"(?im)^[ \t]*(?:description|technical\s+field|field(?:\s+of\s+the\s+invention)?"
    r"|background(?:\s+of\s+the\s+invention)?|cross[- ]reference\b.*)\s*:?\s*$",
)
_STOP_HEADINGS = (
    _H + r"说\s*明\s*书\s*附\s*图",
    _H + r"Anhängende Zeichnungen",
    _H + r"Bezugszeichenliste",
    _H + r"ZITATE ENTHALTEN",
    _H + r"Revendications\s*$",
    _H + r"【図面】",
)
_CJK = "\u3040-\u30ff\u3400-\u9fff\uf900-\ufaff"
# PDF line wraps inside CJK text split words ("复原弹\n簧"); join them so full-text
# search finds the term. Line breaks between Latin words are kept.
_CJK_WRAP_RE = re.compile(rf"(?<=[{_CJK}])\n(?=\S)|(?<=\S)\n(?=[{_CJK}])")


def _unwrap(text: str) -> str:
    return _CJK_WRAP_RE.sub("", text)


_CN_FIRST_CLAIM = re.compile(r"\A\s*1\s*[.、．]\s*\S")
_JP_CLAIM_RE = re.compile(r"【請求項\s*(\d{1,3})】")


def _first(patterns, text: str, start: int) -> int | None:
    found = [m.start() for p in patterns for m in [re.compile(p).search(text, start)] if m]
    return min(found) if found else None


def _locate(pages: list[str]) -> tuple[str, list[tuple[int, int]], dict[str, tuple[int, int]]]:
    """Find claims/description spans by headings in the whole text, not by page."""
    text, offsets = _joined([(i + 1, p) for i, p in enumerate(pages)])
    # The first page is bibliography + abstract; its words must not open a section.
    body = offsets[1][0] if len(offsets) > 2 else 0
    claims_at = _first((_JP_CLAIMS_HEADING,), text, 0)
    if claims_at is None:
        # CNIPA layout: the claims page starts directly with "1." (no text heading).
        for start, _number in offsets[1:]:
            if _CN_FIRST_CLAIM.match(text[start : start + 40]):
                claims_at = start
                break
    if claims_at is None:
        claims_at = _first(_CLAIM_HEADINGS, text, body)
    description_at = _first(_DESCRIPTION_HEADINGS, text, body)
    if claims_at is None and description_at is not None:
        # US A1 layout: claims follow the last numbered paragraph with no heading.
        marks = list(_PARAGRAPH_RE.finditer(text, description_at))
        after = marks[-1].end() if marks else description_at
        first_claim = _US_FIRST_CLAIM.search(text, after)
        if first_claim:
            claims_at = first_claim.start()
    starts = [p for p in (claims_at, description_at) if p is not None]
    stops = [m.start() for p in _STOP_HEADINGS for m in re.compile(p).finditer(text, body)]

    def end_of(position: int) -> int:
        later = [p for p in (*starts, *stops) if p > position]
        return min(later) if later else len(text)

    spans = {}
    if claims_at is not None:
        spans["CLAIMS"] = (claims_at, end_of(claims_at))
    if description_at is not None:
        spans["DESCRIPTION"] = (description_at, end_of(description_at))
    return text, offsets, spans


def _joined(pages: list[tuple[int, str]]) -> tuple[str, list[tuple[int, int]]]:
    """Join page texts and remember where each page starts in the joined string."""
    parts, offsets, position = [], [], 0
    for number, text in pages:
        offsets.append((position, number))
        parts.append(text)
        position += len(text) + 1
    return "\n".join(parts), offsets


def _page_at(offsets: list[tuple[int, int]], index: int) -> int | None:
    page = None
    for start, number in offsets:
        if start <= index:
            page = number
    return page


def _split(text: str, starts: list[int], base: int = 0) -> list[tuple[int, int, str]]:
    bounds = [*starts, len(text)]
    return [
        (base + bounds[i], base + bounds[i + 1], text[bounds[i] : bounds[i + 1]].strip())
        for i in range(len(starts))
        if text[bounds[i] : bounds[i + 1]].strip()
    ]


def _claim_segments(text: str, offsets, span: tuple[int, int]) -> list[Segment]:
    start, end = span
    chunk = text[start:end]
    jp = list(_JP_CLAIM_RE.finditer(chunk))
    matches = jp if jp else list(_CLAIM_RE.finditer(chunk))
    # Keep only an increasing 1, 2, 3 ... sequence so numbered items or claim
    # references inside a claim are not mistaken for new claims.
    kept, expected = [], 1
    for match in matches:
        if int(match.group(1)) == expected:
            kept.append(match)
            expected += 1
    if not kept:
        body = chunk.strip()
        if not body:
            return []
        return [
            Segment(
                "claims", 1, _unwrap(body), _page_at(offsets, start), _page_at(offsets, end - 1)
            )
        ]
    return [
        Segment(
            "claims", ordinal, _unwrap(piece), _page_at(offsets, a),
            _page_at(offsets, max(a, b - 1)),
            claim_number=ordinal,
        )
        for ordinal, (a, b, piece) in enumerate(
            _split(chunk, [m.start() for m in kept], base=start), 1
        )
    ]


def _description_segments(text: str, offsets, span: tuple[int, int]) -> list[Segment]:
    start, end = span
    chunk = text[start:end]
    if not chunk.strip():
        return []
    marks = [m.start() for m in _PARAGRAPH_RE.finditer(chunk)]
    if len(marks) >= 3:
        if marks[0] > 0:
            marks = [0, *marks]
        pieces = _split(chunk, marks, base=start)
    else:
        # No paragraph numbers: chunk at line breaks, ~800 characters each.
        pieces, a, current = [], 0, 0
        for line in chunk.split("\n"):
            current += len(line) + 1
            if current - a >= DESCRIPTION_CHUNK_CHARS:
                pieces.append((start + a, start + current, chunk[a:current].strip()))
                a = current
        if a < len(chunk) and chunk[a:].strip():
            pieces.append((start + a, start + len(chunk), chunk[a:].strip()))
    return [
        Segment("description", ordinal, _unwrap(piece), _page_at(offsets, a),
                _page_at(offsets, max(a, b - 1)))
        for ordinal, (a, b, piece) in enumerate(pieces, 1)
        if piece
    ]


def parse_pdf(pdf_path: str | Path) -> ParsedText:
    try:
        doc = fitz.open(Path(pdf_path))
    except Exception as exc:  # PyMuPDF raises several unrelated types
        return ParsedText(STATUS_FAILED, f"无法打开 PDF：{exc}", ())
    try:
        # NFKC turns full-width digits/brackets (JP/CN PDFs) into plain ones.
        pages = [
            _clean_pdf_text(unicodedata.normalize("NFKC", page.get_text("text")))
            for page in doc
        ]
    finally:
        doc.close()
    total = sum(len(text) for text in pages)
    if not pages or total / len(pages) < MIN_CHARS_PER_PAGE:
        return ParsedText(STATUS_NEEDS_OCR, "PDF 几乎没有文字层（可能是扫描件）", ())
    text, offsets, spans = _locate(pages)
    claims = _claim_segments(text, offsets, spans["CLAIMS"]) if "CLAIMS" in spans else []
    description = (
        _description_segments(text, offsets, spans["DESCRIPTION"])
        if "DESCRIPTION" in spans
        else []
    )
    missing = [
        name
        for name, segments in (("权利要求", claims), ("说明书", description))
        if sum(len(s.text) for s in segments) < MIN_SECTION_CHARS
    ]
    status = STATUS_PARTIAL if missing else STATUS_OK
    detail = f"未识别出：{'、'.join(missing)}" if missing else ""
    return ParsedText(status, detail, (*claims, *description))


# -- writing ---------------------------------------------------------------------


def file_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1 << 20), b""):
            digest.update(block)
    return digest.hexdigest()


def replace_text(
    connection: sqlite3.Connection,
    publication_number: str,
    parsed: ParsedText,
    *,
    source_type: str,
    source_ref: str,
    pdf_sha256: str | None,
) -> None:
    """Replace one publication's stored text atomically (no stale segments remain)."""
    fts = has_fts(connection)
    with connection:
        if fts:
            connection.execute(
                "DELETE FROM library_text_fts WHERE rowid IN "
                "(SELECT segment_id FROM library_text_segment WHERE publication_number = ?)",
                (publication_number,),
            )
        connection.execute(
            "DELETE FROM library_text_segment WHERE publication_number = ?", (publication_number,)
        )
        for segment in parsed.segments:
            cursor = connection.execute(
                """
                INSERT INTO library_text_segment
                    (publication_number, section, ordinal, claim_number, page_start, page_end, text)
                VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    publication_number, segment.section, segment.ordinal, segment.claim_number,
                    segment.page_start, segment.page_end, segment.text,
                ),
            )
            if fts:
                connection.execute(
                    "INSERT INTO library_text_fts(rowid, text) VALUES (?, ?)",
                    (cursor.lastrowid, segment.text),
                )
        connection.execute(
            """
            INSERT INTO library_text_source
                (publication_number, source_type, source_ref, pdf_sha256, status, detail, parsed_at)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(publication_number) DO UPDATE SET
                source_type = excluded.source_type, source_ref = excluded.source_ref,
                pdf_sha256 = excluded.pdf_sha256, status = excluded.status,
                detail = excluded.detail, parsed_at = excluded.parsed_at
            """,
            (
                publication_number, source_type, source_ref, pdf_sha256, parsed.status,
                parsed.detail, datetime.now(UTC).isoformat(timespec="seconds"),
            ),
        )


def index_pdfs(
    connection: sqlite3.Connection,
    items: Iterable[tuple[str, Path | None]],
    *,
    progress: Callable[[int, str], None] | None = None,
    should_cancel: Callable[[], bool] | None = None,
    force: bool = False,
) -> IndexSummary:
    """Index (publication_number, pdf_path) pairs; unchanged PDFs are skipped."""
    summary = IndexSummary()
    for position, (number, pdf) in enumerate(items, 1):
        if should_cancel and should_cancel():
            summary.cancelled = True
            break
        summary.scanned += 1
        if progress:
            progress(position, number)
        if pdf is None:
            summary.no_pdf += 1
            continue
        try:
            digest = file_sha256(pdf)
        except OSError as exc:
            parsed = ParsedText(STATUS_FAILED, f"无法读取 PDF：{exc}", ())
            digest = None
        else:
            row = connection.execute(
                "SELECT pdf_sha256, status FROM library_text_source WHERE publication_number = ?",
                (number,),
            ).fetchone()
            # Re-parsing an unchanged PDF gives the same result, whatever its status.
            if not force and row is not None and row[0] == digest and row[1] != STATUS_FAILED:
                summary.skipped += 1
                continue
            parsed = parse_pdf(pdf)
        replace_text(
            connection, number, parsed, source_type="PDF", source_ref=str(pdf), pdf_sha256=digest
        )
        summary.indexed += 1
        summary.statuses[parsed.status] = summary.statuses.get(parsed.status, 0) + 1
    return summary


def unindexed_items(store) -> list[tuple[str, Path | None]]:
    """Return (publication_number, pdf_path) for patents with PDFs but no index entry."""
    from app.library.models import LibraryQuery
    from app.library.workbench import preferred_library_pdf

    patents = store.query(
        LibraryQuery(limit=max(1, store.count_patents()))
    )
    existing = {
        row[0]
        for row in store.connection.execute(
            "SELECT publication_number FROM library_text_source"
        ).fetchall()
    }
    items = []
    for patent in patents:
        if patent.publication_number in existing:
            continue
        pdf = preferred_library_pdf(patent)
        if pdf is not None:
            items.append((patent.publication_number, pdf))
    return items


# -- reading ---------------------------------------------------------------------


def coverage(connection: sqlite3.Connection) -> dict:
    total = connection.execute("SELECT COUNT(*) FROM library_publication").fetchone()[0]
    rows = connection.execute(
        "SELECT status, COUNT(*) FROM library_text_source GROUP BY status"
    ).fetchall()
    statuses = {row[0]: row[1] for row in rows}
    last = connection.execute("SELECT MAX(parsed_at) FROM library_text_source").fetchone()[0]
    return {
        "publications": total,
        "indexed": sum(statuses.values()),
        "not_indexed": total - sum(statuses.values()),
        "statuses": statuses,
        "last_indexed_at": last,
        "trigram": has_fts(connection),
    }


def text_source(connection: sqlite3.Connection, publication_number: str) -> dict | None:
    row = connection.execute(
        "SELECT source_type, source_ref, status, detail, parsed_at FROM library_text_source "
        "WHERE publication_number = ?",
        (publication_number,),
    ).fetchone()
    if row is None:
        return None
    keys = ("source_type", "source_ref", "status", "detail", "parsed_at")
    return dict(zip(keys, row, strict=True))


def read_segments(
    connection: sqlite3.Connection, publication_number: str, section: str
) -> list[dict]:
    rows = connection.execute(
        """
        SELECT ordinal, claim_number, page_start, page_end, text
        FROM library_text_segment WHERE publication_number = ? AND section = ?
        ORDER BY ordinal
        """,
        (publication_number, section),
    ).fetchall()
    keys = ("ordinal", "claim_number", "page_start", "page_end", "text")
    return [dict(zip(keys, row, strict=True)) for row in rows]


def _term_segment_ids(connection: sqlite3.Connection, term: str, fts: bool) -> set[int]:
    if fts and len(term) >= 3:
        phrase = '"' + term.replace('"', '""') + '"'
        rows = connection.execute(
            "SELECT rowid FROM library_text_fts WHERE library_text_fts MATCH ?", (phrase,)
        ).fetchall()
    else:
        escaped = term.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
        rows = connection.execute(
            "SELECT segment_id FROM library_text_segment WHERE text LIKE ? ESCAPE '\\'",
            (f"%{escaped}%",),
        ).fetchall()
    return {row[0] for row in rows}


def _snippet(text: str, terms: list[str]) -> str:
    lowered = text.casefold()
    positions = [lowered.find(term.casefold()) for term in terms]
    positions = [p for p in positions if p >= 0]
    at = min(positions) if positions else 0
    start, end = max(0, at - SNIPPET_RADIUS), min(len(text), at + SNIPPET_RADIUS * 2)
    body = text[start:end].replace("\n", " ")
    return ("…" if start > 0 else "") + body + ("…" if end < len(text) else "")


def search(
    connection: sqlite3.Connection, terms: list[str], *, match: str = "all"
) -> tuple[list[Hit], list[str]]:
    """Return hits ordered by matched-segment count, plus notes about the method used."""
    terms = [t.strip() for t in terms if t and t.strip()]
    if not terms:
        return [], []
    fts = has_fts(connection)
    notes = []
    short = [t for t in terms if len(t) < 3 or not fts]
    if short:
        notes.append(
            "以下检索词少于 3 个字或全文索引不可用，改用模糊匹配（较慢）：" + "、".join(short)
        )
    per_term = {term: _term_segment_ids(connection, term, fts) for term in terms}
    all_ids = set().union(*per_term.values())
    if not all_ids:
        return [], notes
    placeholders = ",".join("?" * len(all_ids))
    rows = connection.execute(
        f"""
        SELECT segment_id, publication_number, section, ordinal, claim_number, page_start, text
        FROM library_text_segment WHERE segment_id IN ({placeholders})
        """,
        tuple(all_ids),
    ).fetchall()
    by_pub: dict[str, list[tuple]] = {}
    for row in rows:
        by_pub.setdefault(row[1], []).append(row)
    hits = []
    for number, segments in by_pub.items():
        ids = {row[0] for row in segments}
        matched_terms = [term for term in terms if per_term[term] & ids]
        if match == "all" and len(matched_terms) < len(terms):
            continue
        segments.sort(key=lambda r: (r[2] != "claims", r[3]))
        snippets = tuple(
            {
                "section": row[2],
                "ordinal": row[3],
                "claim_number": row[4],
                "page": row[5],
                "text": _snippet(row[6], terms),
            }
            for row in segments[:MAX_SNIPPETS]
        )
        hits.append(Hit(number, len(segments), snippets))
    hits.sort(key=lambda hit: (-hit.matched_segments, hit.publication_number))
    return hits, notes
