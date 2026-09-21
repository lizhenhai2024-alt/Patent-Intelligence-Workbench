import os

import pytest

from app.desktop.app import PatentWorkbenchApp
from app.desktop.runtime import DesktopRuntime
from app.domain.search import SearchHit, SearchMode, SearchPage, SearchResponse

pytestmark = pytest.mark.skipif(
    os.name != "nt" and not os.environ.get("DISPLAY"),
    reason="Tk UI tests require a display",
)


def test_search_classifier_uses_abstract_and_classification():
    runtime = DesktopRuntime.create()
    app = PatentWorkbenchApp(runtime)
    app.withdraw()
    hit = SearchHit(
        publication_number="EP1234567A1",
        jurisdiction="EP",
        title="Vehicle suspension device",
        abstract="An upper spring seat supports a coil spring.",
        applicants=("Example Corp",),
        classifications=("B60G11/16",),
    )
    response = SearchResponse(
        mode=SearchMode.TEXT,
        provider="test",
        page=SearchPage(hits=(hit,), total_result_count=1),
        normalized_query="suspension",
    )
    app._render_search_response(response)
    values = app.search_tree.item(hit.publication_number, "values")
    assert "Spring Seat" in values[3]

    app.search_tree.selection_set(hit.publication_number)
    app._render_search_technology_evidence()
    evidence = app.search_technology_var.get()
    assert "Spring Seat" in evidence
    assert "B60G11" in evidence
    app.destroy()
    runtime.close()
