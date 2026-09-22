from datetime import UTC, date, datetime

import pytest

from app.domain.family import FamilyType, PatentFamily, PatentPublication
from app.intelligence.ai_packet import build_ai_prompt
from app.intelligence.analysis import AnalysisScope, AnalysisService
from app.intelligence.report import render_html, save_html
from app.intelligence.search_plan import plan_search
from app.intelligence.watch_review import WatchReviewStore
from app.library.store import SQLitePatentLibrary


@pytest.fixture
def library(tmp_path):
    store = SQLitePatentLibrary(tmp_path / "workbench.db")
    family = PatentFamily(
        family_type=FamilyType.DOCDB_SIMPLE,
        source="TEST",
        source_family_id="F-1",
        members=[
            PatentPublication(
                publication_number="US20240000001A1",
                jurisdiction="US",
                title="<Damper> pilot valve",
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
    store.upsert_family(family)
    for number in ("US20240000001A1", "EP4000001A1"):
        store.add_company_group(number, "astemo")
        store.add_technology_topic(number, "pilot_valve")
        store.add_technology_topic(number, "semi_active")
    store.upsert_publication(
        PatentPublication(
            publication_number="CN120000001A",
            jurisdiction="CN",
            title="减振器密封结构",
            publication_date=date(2025, 3, 4),
        )
    )
    store.add_company_group("CN120000001A", "kyb")
    yield store
    store.close()


def test_landscape_keeps_family_and_national_counts_separate(library):
    report = AnalysisService(library).landscape(AnalysisScope())
    assert [(m.label, m.value) for m in report.metrics] == [
        ("已知专利族", 1),
        ("国家公开件", 3),
        ("家族未解析公开件", 1),
    ]
    trend = next(section for section in report.sections if section.title.startswith("申请趋势"))
    assert trend.rows[0].cells == ("2022", "1", "申请日")
    assert set(trend.rows[0].publication_numbers) == {"US20240000001A1", "EP4000001A1"}
    html = render_html(report)
    assert "&lt;Damper&gt;" not in html  # titles do not leak into aggregate labels
    assert "US20240000001A1" in html
    assert "family_key" in html


def test_company_profile_uses_exact_group_membership(library):
    service = AnalysisService(library)
    report = service.company_profile(AnalysisScope(), "ASTEMO")
    assert report.metrics[1].value == 2
    assert "CN120000001A" not in render_html(report)
    with pytest.raises(KeyError):
        service.company_profile(AnalysisScope(), "Ast")


def test_topic_scope_uses_technical_fields_and_html_escapes(library, tmp_path):
    service = AnalysisService(library)
    report = service.landscape(AnalysisScope(topic="<Damper>"))
    assert report.metrics[1].value == 1
    html = render_html(report)
    assert "&lt;Damper&gt;" in html
    assert "<Damper>" not in html
    assert save_html(report, tmp_path / "landscape.html").read_text(encoding="utf-8") == html
    with pytest.raises(ValueError):
        save_html(report, tmp_path / "landscape.txt")


def test_competition_and_route_comparison_have_receipts(library):
    service = AnalysisService(library)
    competition = service.competitive_landscape(AnalysisScope(), ("astemo", "kyb"))
    rows = competition.sections[0].rows
    assert rows[0].cells[1] == "1"
    assert rows[1].cells[1] == "0"  # unresolved CN record is not a fabricated family
    assert competition.sections[1].rows[0].cells[1] == "0"
    assert competition.sections[2].rows[0].publication_numbers == (
        "EP4000001A1",
        "US20240000001A1",
    )
    routes = service.route_comparison(AnalysisScope(), ("pilot_valve", "semi_active"))
    assert routes.sections[1].rows[0].publication_numbers == (
        "EP4000001A1",
        "US20240000001A1",
    )
    assert routes.sections[2].rows[0].cells[1] == "0"


def test_problem_plan_is_preview_only():
    plan = plan_search("CDC 减振器低温响应变慢")
    assert any(group.topic_id == "continuous_damping_control" for group in plan.groups)
    assert any("damper" in term.casefold() for group in plan.groups for term in group.terms)
    assert plan.editable_query
    assert plan_search("未知术语测试").unmatched


def test_watch_review_persists_and_does_not_change_event(library):
    library.add_watch_source(
        "US20240000001A1",
        "watch-1",
        event_type="NEW_FAMILY",
        detected_at=datetime(2026, 9, 22, tzinfo=UTC),
    )
    review = WatchReviewStore(library.path)
    item = review.list_items()[0]
    assert item.status == "pending"
    review.set_review(item, status="important", note="检查阀结构")
    review.close()

    reopened = WatchReviewStore(library.path)
    saved = reopened.list_items()[0]
    assert (saved.status, saved.note, saved.event_type) == (
        "important",
        "检查阀结构",
        "NEW_FAMILY",
    )
    assert reopened.brief().metrics[0].value == 1
    assert library.get_patent(item.publication_number).watch_rule_ids == ("watch-1",)
    reopened.close()


def test_ai_packet_keeps_sources_scope_and_limits_without_model_call(library):
    report = AnalysisService(library).landscape(AnalysisScope(topic="pilot_valve"))
    packet = build_ai_prompt(report, max_rows_per_section=1)
    assert "US20240000001A1" in packet
    assert "family_key" in packet
    assert "侵权、FTO" in packet
    assert "只有手动" not in packet
    assert "主动复制" in packet
    with pytest.raises(ValueError):
        build_ai_prompt(report, max_rows_per_section=0)
