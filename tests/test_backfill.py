import pytest

from app.domain.family import PatentPublication
from app.library import backfill, fulltext
from app.library.store import SQLitePatentLibrary
from app.providers.base import ProviderAuthenticationError

CLAIMS_TEXT = (
    "1. A damper comprising a rebound spring assembly and a piston rod.\n"
    "2. The damper of claim 1, wherein the rebound spring assembly comprises "
    "a buffer washer and a collar with several claws, the claws being biased "
    "inward to grip the piston rod firmly during high-frequency oscillation "
    "of the vehicle suspension so as to prevent rattling noise over the life "
    "of the damper assembly under repeated compression and rebound cycles."
)
DESCRIPTION_TEXT = (
    "[0001] The present invention relates to a vehicle damper, in particular "
    "to a mounting structure for a rebound spring. " + ("x" * 200) + "\n"
    "[0002] The claws engage the piston to reduce chatter noise during "
    "high-frequency motion. " + ("y" * 200)
)


@pytest.fixture
def library(tmp_path):
    path = tmp_path / "workbench.db"
    store = SQLitePatentLibrary(path)
    for number in ("US20180003259A1", "US20250290554A1", "CN222863977U"):
        store.upsert_publication(
            PatentPublication(publication_number=number, jurisdiction=number[:2], title="减振器")
        )
    fulltext.ensure_fulltext_schema(store.connection)
    yield store
    store.close()


def _fake_run_coroutine(awaitable):
    # The stubs below are plain values wrapped as no-op awaitables by the fake
    # fetch_section, so nothing here needs a real event loop.
    return awaitable


def _stub_fetch(section_text: dict[str, dict[str, str]], *, raise_on: set[str] = frozenset()):
    async def fetch_section(provider, patent, section):
        if patent.canonical in raise_on:
            raise ProviderAuthenticationError("bad credentials")
        return section_text.get(patent.canonical, {}).get(section, "")

    return fetch_section


def test_candidates_lists_missing_and_poor_text_only(library):
    store = library
    fulltext.replace_text(
        store.connection,
        "CN222863977U",
        fulltext.ParsedText(fulltext.STATUS_OK, "", ()),
        source_type="PDF",
        source_ref="x.pdf",
        pdf_sha256="abc",
    )
    items = backfill.candidates(store.connection)
    assert set(items) == {"US20180003259A1", "US20250290554A1"}


def test_run_backfill_fills_text_and_records_provenance(library):
    store = library
    items = ["US20180003259A1"]
    fetch = _stub_fetch(
        {"US20180003259A1": {"claims": CLAIMS_TEXT, "description": DESCRIPTION_TEXT}}
    )
    summary = backfill.run_backfill(
        store,
        provider=object(),
        publication_numbers=items,
        fetch_section=fetch,
        delay_seconds=0,
        sleep=lambda _s: None,
        run_coroutine=lambda coro: __import__("asyncio").run(coro),
    )
    assert summary.filled == 1
    assert summary.errors == 0
    source = fulltext.text_source(store.connection, "US20180003259A1")
    assert source["source_type"] == "EPO_OPS"
    assert source["status"] == fulltext.STATUS_OK
    hits, _ = fulltext.search(store.connection, ["rebound spring"], match="all")
    assert any(h.publication_number == "US20180003259A1" for h in hits)
    row = store.connection.execute(
        "SELECT source_type FROM library_provenance WHERE publication_number = ?",
        ("US20180003259A1",),
    ).fetchone()
    assert row["source_type"] == "BACKFILL"


def test_run_backfill_no_data_and_error_do_not_stop_the_batch(library):
    store = library
    items = ["US20180003259A1", "US20250290554A1"]
    fetch = _stub_fetch({}, raise_on={"US20250290554A1"})
    summary = backfill.run_backfill(
        store,
        provider=object(),
        publication_numbers=items,
        fetch_section=fetch,
        delay_seconds=0,
        sleep=lambda _s: None,
        run_coroutine=lambda coro: __import__("asyncio").run(coro),
    )
    assert summary.scanned == 2
    assert summary.no_data == 1
    assert summary.errors == 1
    assert summary.filled == 0
    assert fulltext.text_source(store.connection, "US20180003259A1") is None


def test_run_backfill_cancel_stops_early(library):
    store = library
    items = ["US20180003259A1", "US20250290554A1"]
    fetch = _stub_fetch(
        {"US20180003259A1": {"claims": CLAIMS_TEXT, "description": DESCRIPTION_TEXT}}
    )
    summary = backfill.run_backfill(
        store,
        provider=object(),
        publication_numbers=items,
        fetch_section=fetch,
        delay_seconds=0,
        sleep=lambda _s: None,
        run_coroutine=lambda coro: __import__("asyncio").run(coro),
        should_cancel=lambda: True,
    )
    assert summary.cancelled is True
    assert summary.scanned == 0
    assert summary.filled == 0


def test_write_task_log(tmp_path):
    summary = backfill.BackfillSummary(task_id="backfill-test-1")
    summary.filled = 2
    summary.outcomes.append(backfill.BackfillOutcome("US1", "filled", "ok"))
    path = backfill.write_task_log(tmp_path / "backfill_runs", summary, limit=200)
    assert path.exists()
    assert "backfill-test-1" in path.read_text(encoding="utf-8")
