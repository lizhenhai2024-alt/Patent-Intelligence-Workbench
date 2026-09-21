from app.core.technology_classifier import TechnologyClassifier
from app.domain.search import SearchHit


def test_search_classifier_uses_abstract_and_classification():
    hit = SearchHit(
        publication_number="EP1234567A1",
        jurisdiction="EP",
        title="Vehicle suspension device",
        abstract="An upper spring seat supports a coil spring.",
        applicants=("Example Corp",),
        classifications=("B60G11/16",),
    )
    text = " ".join(part for part in (hit.title or "", hit.abstract or "") if part)
    matches = TechnologyClassifier().classify(
        text=text,
        classifications=hit.classifications,
    )
    spring_seat = next(match for match in matches if match.node_id == "spring_seat")
    assert "upper spring seat" in spring_seat.matched_terms
    assert spring_seat.matched_classifications == ("B60G11",)
