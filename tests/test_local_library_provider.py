from types import SimpleNamespace

from app.domain.search import SearchExpression
from app.library.models import LibraryClassification
from app.providers.local_library import _matches_expression


def _patent(*, title: str, classifications=()):
    return SimpleNamespace(
        publication_number="US1234567A1",
        title=title,
        original_assignees=("Bose Corporation",),
        current_assignees=(),
        company_groups=(),
        technology_topics=(),
        projects=(),
        tags=(),
        publication_date=None,
        classifications=tuple(classifications),
    )


def _portfolio_expression():
    return SearchExpression(
        applicants=("Bose Corporation",),
        portfolio_terms=(
            "vehicle suspension",
            "active suspension",
            "shock absorber",
            "suspension damper",
        ),
        portfolio_classifications=("B60G17", "F16F9/46"),
    )


def test_local_portfolio_rejects_bose_acoustic_false_positive():
    patent = _patent(
        title="Balanced acoustic device with passive radiators",
        classifications=(LibraryClassification("CPC", "H04R1/28"),),
    )

    assert not _matches_expression(patent, _portfolio_expression())


def test_local_portfolio_accepts_vehicle_suspension_text():
    patent = _patent(title="Active Suspension System")

    assert _matches_expression(patent, _portfolio_expression())


def test_local_portfolio_accepts_strong_suspension_classification():
    patent = _patent(
        title="Counter-Rotating Motors with Linear Output",
        classifications=(LibraryClassification("CPC", "B60G17/00AI"),),
    )

    assert _matches_expression(patent, _portfolio_expression())
