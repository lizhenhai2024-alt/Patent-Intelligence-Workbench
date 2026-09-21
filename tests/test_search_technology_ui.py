from datetime import date

import pytest

from app.desktop.app import PatentWorkbenchApp
from app.desktop.runtime import DesktopRuntime
from app.desktop.tk_runtime import can_run_tk_tests
from app.domain.search import SearchHit, SearchMode, SearchPage, SearchResponse

pytestmark = pytest.mark.skipif(
    not can_run_tk_tests(),
    reason="Tk UI tests require a usable Tcl/Tk runtime",
)


def test_search_results_show_technology_tags_and_evidence():
    runtime = DesktopRuntime.create()
    app = PatentWorkbenchApp(runtime)
    app.withdraw()
    hit = SearchHit(
        publication_number="US20240000001A1",
        jurisdiction="US",
        title=(
            "Pilot controlled damper with floating piston, pilot pressure chamber, "
            "and fail safe valve"
        ),
        applicants=("Example Corp",),
        publication_date=date(2024, 1, 4),
    )
    response = SearchResponse(
        mode=SearchMode.TEXT,
        provider="test",
        page=SearchPage(hits=(hit,), total_result_count=1),
        normalized_query="pilot damper",
    )
    app._render_search_response(response)
    values = app.search_tree.item(hit.publication_number, "values")
    assert "Semi-active" in values[3]
    assert "Floating Piston" in values[3]
    assert "Pilot Valve" in values[3]
    assert "Back-pressure Control" in values[3]
    assert "Fail-safe Valve" in values[3]

    app.search_tree.selection_set(hit.publication_number)
    app._render_search_technology_evidence()
    evidence = app.search_technology_var.get()
    assert "Floating Piston" in evidence
    assert "Fail-safe Valve" in evidence
    assert "pilot pressure chamber" in evidence
    app.destroy()
    runtime.close()
