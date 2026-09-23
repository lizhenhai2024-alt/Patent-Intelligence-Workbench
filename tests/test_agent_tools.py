import hashlib
import json
import sqlite3
from datetime import date

import pymupdf as fitz
import pytest

from app.agent_tools.tools import TOOL_NAMES, LibraryTools, ToolError, open_read_only
from app.domain.family import FamilyType, PatentFamily, PatentPublication
from app.library.store import SQLitePatentLibrary

PRIVATE_VALUES = ("SECRET-NOTE-PX9", "SECRET-PROJECT-PX9", "SECRET-TAG-PX9", "secret-rule-px9")


def _write_pdf(path):
    doc = fitz.open()
    for text in (
        "Bibliography",
        "1. A damper comprising a pilot valve.\n2. The damper of claim 1.",
        "FIELD\n[0001] The disclosure relates to semi-active dampers.",
    ):
        doc.new_page().insert_text((72, 72), text)
    doc.save(path)
    doc.close()


@pytest.fixture
def db_path(tmp_path):
    path = tmp_path / "workbench.db"
    store = SQLitePatentLibrary(path)
    store.upsert_family(
        PatentFamily(
            family_type=FamilyType.DOCDB_SIMPLE,
            source="TEST",
            source_family_id="F-1",
            members=[
                PatentPublication(
                    publication_number="US20240000001A1",
                    jurisdiction="US",
                    title="Damper pilot valve",
                    filing_date=date(2022, 1, 2),
                    publication_date=date(2024, 1, 2),
                ),
                PatentPublication(
                    publication_number="EP4000001A1",
                    jurisdiction="EP",
                    title="Suspension pilot valve",
                    publication_date=date(2024, 2, 2),
                ),
            ],
        )
    )
    for number in ("US20240000001A1", "EP4000001A1"):
        store.add_company_group(number, "astemo")
        store.add_technology_topic(number, "pilot_valve")
    store.upsert_publication(
        PatentPublication(
            publication_number="CN120000001A",
            jurisdiction="CN",
            title="减振器密封结构",
            filing_date=date(2019, 5, 6),
            publication_date=date(2025, 3, 4),
        )
    )
    store.add_company_group("CN120000001A", "kyb")
    # Private annotations: "pilot" in the note must not make CN120000001A a text hit.
    store.set_note("CN120000001A", "SECRET-NOTE-PX9 pilot")
    store.add_project("CN120000001A", "SECRET-PROJECT-PX9")
    store.add_tag("CN120000001A", "SECRET-TAG-PX9")
    store.add_watch_source("CN120000001A", "secret-rule-px9")
    pdf = tmp_path / "US20240000001A1.pdf"
    _write_pdf(pdf)
    store.attach_pdf("US20240000001A1", pdf)
    store.close()
    return path


@pytest.fixture
def tools(db_path):
    library_tools = open_read_only(db_path)
    yield library_tools
    library_tools.store.close()


def _all_calls(tools):
    return [
        tools.library_status(),
        tools.list_companies(),
        tools.list_technology_topics(),
        tools.search_library(),
        tools.search_library(text="pilot"),
        tools.search_library(company="KYB", from_date="2019-01-01"),
        tools.get_publication("CN120000001A"),
        tools.read_publication_text("US20240000001A1", "claims"),
        tools.read_publication_text("EP4000001A1"),
        tools.get_family(publication_number="EP4000001A1"),
        tools.get_family(publication_number="CN120000001A"),
        tools.run_landscape(),
        tools.run_company_profile("astemo"),
        tools.run_comparison(companies=["astemo", "kyb"]),
    ]


def test_tool_names_are_the_public_surface():
    assert len(TOOL_NAMES) == 10
    assert all(callable(getattr(LibraryTools, name)) for name in TOOL_NAMES)


def test_every_result_uses_the_envelope_and_receipts_exist(tools):
    known = {"US20240000001A1", "EP4000001A1", "CN120000001A"}
    for result in _all_calls(tools):
        assert set(result) == {"data", "receipts", "source", "as_of", "truncated", "notes"}
        assert result["source"] == "LocalLibrary"
        assert set(result["receipts"]) <= known
        json.dumps(result, ensure_ascii=False)


def test_publication_results_always_carry_receipts(tools):
    search = tools.search_library()
    assert search["receipts"] == sorted(r["publication_number"] for r in search["data"]["results"])
    assert tools.get_publication("EP4000001A1")["receipts"] == ["EP4000001A1"]
    family = tools.get_family(family_key=tools.get_publication("EP4000001A1")["data"]["family_key"])
    assert family["receipts"] == ["EP4000001A1", "US20240000001A1"]
    report = tools.run_landscape()
    assert set(report["receipts"]) == {"US20240000001A1", "EP4000001A1", "CN120000001A"}
    rows = [row for section in report["data"]["sections"] for row in section["rows"]]
    assert all("publication_numbers" in row for row in rows)


def test_private_annotations_never_leave_the_tools(tools):
    text = json.dumps(_all_calls(tools), ensure_ascii=False)
    for value in PRIVATE_VALUES:
        assert value not in text


def test_text_search_ignores_private_notes(tools):
    results = tools.search_library(text="pilot")["data"]["results"]
    numbers = {r["publication_number"] for r in results}
    assert numbers == {"US20240000001A1", "EP4000001A1"}


def test_company_resolution_is_exact(tools):
    assert tools.search_library(company="KYB")["receipts"] == ["CN120000001A"]
    with pytest.raises(ToolError, match="精确匹配"):
        tools.search_library(company="KY")
    with pytest.raises(ToolError):
        tools.run_comparison(companies=["astemo", "Ast"])


def test_search_limits_dates_and_truncation(tools):
    result = tools.search_library(limit=1)
    assert result["truncated"] is True
    assert result["data"]["total_matches"] == 3
    assert tools.search_library(from_date="2020-01-01", to_date="2022-12-31")["receipts"] == [
        "US20240000001A1"
    ]
    with pytest.raises(ToolError):
        tools.search_library(limit=101)
    with pytest.raises(ToolError):
        tools.search_library(from_date="2024/01/01")


def test_read_publication_text_uses_local_pdf_only(tools):
    # Not indexed yet: the tool parses the local PDF on the fly (read-only, no network).
    claims = tools.read_publication_text("US20240000001A1", "claims", max_chars=10)
    assert claims["data"]["available"] is True
    assert claims["data"]["segments"][0]["text"] == "1. A damper"[:10]
    assert claims["data"]["segments"][0]["claim_number"] == 1
    assert claims["truncated"] is True
    assert any("尚未建全文索引" in note for note in claims["notes"])
    second = tools.read_publication_text("US20240000001A1", "claims", claims=[2])
    assert [s["claim_number"] for s in second["data"]["segments"]] == [2]
    description = tools.read_publication_text("US20240000001A1", "description")
    assert "[0001]" in description["data"]["segments"][0]["text"]
    missing = tools.read_publication_text("EP4000001A1")
    assert missing["data"]["available"] is False and missing["receipts"] == []
    with pytest.raises(ToolError):
        tools.read_publication_text("US20240000001A1", "abstract")
    with pytest.raises(ToolError):
        tools.get_publication("US99999999A1")


def test_comparison_argument_rules(tools):
    with pytest.raises(ToolError):
        tools.run_comparison()
    with pytest.raises(ToolError):
        tools.run_comparison(companies=["astemo"], routes=["pilot_valve"])
    with pytest.raises(ToolError):
        tools.run_comparison(companies=["astemo"])


def test_tools_never_modify_the_database(db_path):
    before = hashlib.sha256(db_path.read_bytes()).hexdigest()
    library_tools = open_read_only(db_path)
    _all_calls(library_tools)
    library_tools.store.close()
    assert hashlib.sha256(db_path.read_bytes()).hexdigest() == before


def test_read_only_store_refuses_writes_and_missing_files(db_path, tmp_path):
    store = SQLitePatentLibrary(db_path, read_only=True)
    with pytest.raises(sqlite3.OperationalError):
        store.set_note("CN120000001A", "x")
    store.close()
    with pytest.raises(FileNotFoundError):
        SQLitePatentLibrary(tmp_path / "missing.db", read_only=True)
    assert not (tmp_path / "missing.db").exists()


def test_mcp_server_lists_exactly_the_read_only_tools(tools):
    pytest.importorskip("mcp")
    import asyncio

    from app.agent_tools.mcp_server import build_server

    listed = asyncio.run(build_server(tools).list_tools())
    assert sorted(tool.name for tool in listed) == sorted(TOOL_NAMES)
    assert all(tool.annotations.readOnlyHint for tool in listed)
