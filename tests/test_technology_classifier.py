from app.core.technology_classifier import TechnologyClassifier
from app.core.technology_taxonomy import TechnologyTaxonomy


def test_taxonomy_metadata_is_loaded_and_backward_compatible():
    taxonomy = TechnologyTaxonomy.default()
    spring_seat = taxonomy.find("spring_seat")
    assert spring_seat.level == "component"
    assert "spring perch" in spring_seat.aliases
    assert "B60G11" in spring_seat.classifications
    assert "valve spring seat" in spring_seat.exclude_terms
    assert taxonomy.find("base_valve").level == ""


def test_classifier_distinguishes_spring_seat_from_valve_spring_seat():
    classifier = TechnologyClassifier()
    matches = classifier.classify(text="Upper spring seat and spring perch for vehicle suspension")
    assert any(match.node_id == "spring_seat" for match in matches)

    excluded = classifier.classify(text="A valve spring seat supports the pilot valve spring")
    assert not any(match.node_id == "spring_seat" for match in excluded)


def test_classifier_separates_control_and_gas_separating_pistons():
    classifier = TechnologyClassifier()
    control = classifier.classify(text="Pilot controlled damper uses a control floating piston")
    assert any(match.node_id == "floating_piston" for match in control)
    assert not any(match.node_id == "separating_piston" for match in control)

    separator = classifier.classify(text="Monotube damper has an oil gas separating piston")
    assert any(match.node_id == "separating_piston" for match in separator)
    assert not any(match.node_id == "floating_piston" for match in separator)


def test_classifier_uses_classifications_as_strong_evidence():
    classifier = TechnologyClassifier()
    matches = classifier.classify(text="", classifications=("B60G11/16",))
    spring_seat = next(match for match in matches if match.node_id == "spring_seat")
    assert spring_seat.score == 3
    assert spring_seat.matched_classifications == ("B60G11",)
