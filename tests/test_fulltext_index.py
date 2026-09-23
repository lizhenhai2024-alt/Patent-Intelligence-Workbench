import hashlib

import pymupdf as fitz
import pytest

from app.agent_tools.tools import ToolError, open_read_only
from app.domain.family import PatentPublication
from app.library import fulltext
from app.library.store import SQLitePatentLibrary

CLAIMS_PAGE = (
    "1. 一种减振器，其特征在于，包括复原弹簧总成和活塞杆。\n"
    "2. 根据权利要求1所述的减振器，其特征在于，所述复原弹簧总成包括缓冲垫圈和套环，"
    "所述套环设有多个卡爪。\n"
    "3. 根据权利要求2所述的减振器，其特征在于，所述卡爪偏斜朝内。"
)
DESCRIPTION_PAGE = (
    "技术领域\n[0001] 本发明涉及汽车减振器，特别是复原弹簧的固定结构。\n"
    "[0002] 现有技术中缓冲垫圈与活塞松配合，高频运动时产生窜动噪音。\n"
    "[0003] 本发明通过卡爪紧配解决阀芯窜动问题。"
)


def _cjk_pdf(path, pages):
    doc = fitz.open()
    for text in pages:
        page = doc.new_page()
        page.insert_textbox(fitz.Rect(40, 40, 560, 800), text, fontname="china-s", fontsize=10)
    doc.save(path)
    doc.close()


@pytest.fixture
def library(tmp_path):
    path = tmp_path / "workbench.db"
    store = SQLitePatentLibrary(path)
    for number in ("CN222863977U", "CN100000001A", "CN100000002A"):
        store.upsert_publication(
            PatentPublication(publication_number=number, jurisdiction="CN", title="减振器")
        )
    pdf = tmp_path / "CN222863977U.pdf"
    _cjk_pdf(pdf, ["说明书摘要", CLAIMS_PAGE, DESCRIPTION_PAGE])
    store.attach_pdf("CN222863977U", pdf)
    scanned = tmp_path / "CN100000001A.pdf"
    doc = fitz.open()
    doc.new_page()
    doc.save(scanned)
    doc.close()
    store.attach_pdf("CN100000001A", scanned)
    store.set_note("CN100000002A", "复原弹簧 私密笔记")
    yield store, path, pdf
    store.close()


def _items(store):
    from app.library.models import LibraryQuery
    from app.library.workbench import preferred_library_pdf

    return [(p.publication_number, preferred_library_pdf(p)) for p in store.query(LibraryQuery())]


def test_trigram_is_available_and_schema_is_created(library):
    store, _, _ = library
    assert store.fulltext_trigram is True
    assert fulltext.tables_exist(store.connection)


def test_parse_splits_claims_by_number_and_description_by_paragraph(library):
    _, _, pdf = library
    parsed = fulltext.parse_pdf(pdf)
    claims = [s for s in parsed.segments if s.section == "claims"]
    description = [s for s in parsed.segments if s.section == "description"]
    assert [s.claim_number for s in claims] == [1, 2, 3]
    assert all(s.page_start == 2 for s in claims)
    assert "卡爪" in claims[1].text
    assert any("[0002]" in s.text for s in description)
    assert all(s.page_start == 3 for s in description)


def test_scanned_pdf_is_marked_needs_ocr(tmp_path):
    pdf = tmp_path / "scan.pdf"
    doc = fitz.open()
    doc.new_page()
    doc.save(pdf)
    doc.close()
    assert fulltext.parse_pdf(pdf).status == fulltext.STATUS_NEEDS_OCR


def test_index_is_incremental_and_replaces_stale_text(library, tmp_path):
    store, _, pdf = library
    first = fulltext.index_pdfs(store.connection, _items(store))
    assert first.indexed == 2 and first.no_pdf == 1
    assert first.statuses[fulltext.STATUS_NEEDS_OCR] == 1
    again = fulltext.index_pdfs(store.connection, _items(store))
    assert again.skipped == 2 and again.indexed == 0  # unchanged PDFs are skipped
    count = store.connection.execute("SELECT COUNT(*) FROM library_text_segment").fetchone()[0]
    _cjk_pdf(pdf, ["摘要", "1. 一种全新的空气弹簧。", "技术领域\n[0001] 空气弹簧。"])
    fulltext.index_pdfs(store.connection, _items(store))
    rows = store.connection.execute(
        "SELECT text FROM library_text_segment WHERE publication_number='CN222863977U'"
    ).fetchall()
    assert all("复原弹簧" not in row[0] for row in rows)
    assert len(rows) < count
    hits, _ = fulltext.search(store.connection, ["复原弹簧"])
    assert hits == []  # FTS rows were replaced too


def test_search_trigram_short_term_fallback_and_match_modes(library):
    store, _, _ = library
    fulltext.index_pdfs(store.connection, _items(store))
    hits, notes = fulltext.search(store.connection, ["复原弹簧"])
    assert [h.publication_number for h in hits] == ["CN222863977U"]
    snippet = hits[0].snippets[0]
    assert snippet["section"] == "claims" and "复原弹簧" in snippet["text"]
    assert notes == []
    short, short_notes = fulltext.search(store.connection, ["阀芯"])
    assert [h.publication_number for h in short] == ["CN222863977U"]
    assert short_notes and "模糊匹配" in short_notes[0]
    assert fulltext.search(store.connection, ["复原弹簧", "空气悬架"], match="all")[0] == []
    assert len(fulltext.search(store.connection, ["复原弹簧", "空气悬架"], match="any")[0]) == 1


def test_agent_tools_fulltext_search_and_cached_read(library):
    store, path, _ = library
    fulltext.index_pdfs(store.connection, _items(store))
    before = hashlib.sha256(path.read_bytes()).hexdigest()
    tools = open_read_only(path)
    try:
        result = tools.search_library(fulltext=["复原弹簧"])
        assert result["receipts"] == ["CN222863977U"]  # the private note is never searched
        hit = result["data"]["results"][0]
        assert hit["snippets"][0]["claim_number"] == 1
        assert any("未索引" in note for note in result["notes"])
        claims = tools.read_publication_text("CN222863977U", "claims", claims=[2, 3])
        assert [s["claim_number"] for s in claims["data"]["segments"]] == [2, 3]
        assert claims["data"]["source_type"] == "PDF"
        status = tools.library_status()["data"]["fulltext_index"]
        assert status["indexed"] == 2 and status["statuses"]["needs_ocr"] == 1
        with pytest.raises(ToolError):
            tools.search_library(fulltext=["弹簧"], match="some")
    finally:
        tools.store.close()
    assert hashlib.sha256(path.read_bytes()).hexdigest() == before


def test_fulltext_search_without_index_is_explained(tmp_path):
    path = tmp_path / "old.db"
    import sqlite3

    sqlite3.connect(path).execute(
        "CREATE TABLE library_publication (publication_number TEXT PRIMARY KEY)"
    ).connection.close()
    # A read-only open of a database that predates the full-text tables.
    tools = open_read_only(path)
    try:
        with pytest.raises(ToolError, match="尚未建立全文索引"):
            tools.search_library(fulltext=["复原弹簧"])
    finally:
        tools.store.close()


def test_desktop_update_fulltext_index_button(tmp_path):
    import time

    from app.desktop.tk_runtime import can_run_tk_tests

    if not can_run_tk_tests():
        pytest.skip("Tk UI tests require a usable Tcl/Tk runtime")
    from app.desktop.app import PatentWorkbenchApp
    from app.desktop.fulltext_ui import run_fulltext_index
    from app.desktop.paths import AppPaths
    from app.desktop.runtime import DesktopRuntime

    runtime = DesktopRuntime.create(paths=AppPaths.for_root(tmp_path / "appdata"))
    pdf = tmp_path / "CN222863977U.pdf"
    _cjk_pdf(pdf, ["说明书摘要", CLAIMS_PAGE, DESCRIPTION_PAGE])
    runtime.library_store.upsert_publication(
        PatentPublication(publication_number="CN222863977U", jurisdiction="CN", title="减振器")
    )
    runtime.library_store.attach_pdf("CN222863977U", pdf)
    app = PatentWorkbenchApp(runtime)
    app.withdraw()
    try:
        assert "已索引 0 / 1" in app.fulltext_status_var.get()
        run_fulltext_index(app)
        deadline = time.monotonic() + 5
        while app._fulltext_cancel is not None and time.monotonic() < deadline:
            app.update()
            time.sleep(0.01)
        assert "全文索引完成" in app.fulltext_status_var.get()
        assert "已索引 1 / 1" in app.fulltext_status_var.get()
    finally:
        app.destroy()


def test_cjk_line_wraps_are_joined_so_split_terms_are_found():
    assert fulltext._unwrap("所述复原弹\n簧总成包括(1)\n的底部") == "所述复原弹簧总成包括(1)的底部"
    assert fulltext._unwrap("a pilot\nvalve") == "a pilot\nvalve"
