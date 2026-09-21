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


def test_classifier_normalizes_hyphenated_engineering_terms():
    classifier = TechnologyClassifier()
    matches = classifier.classify(
        text="Frequency-dependent electronic damping for a vehicle damper"
    )
    assert any(match.node_id == "fsd" for match in matches)


def test_classifier_handles_chinese_cdc_architecture_terms():
    classifier = TechnologyClassifier()
    matches = classifier.classify(
        text="双电磁阀减振器采用先导阀、背压腔和浮动活塞，并具备故障安全功能"
    )
    ids = {match.node_id for match in matches}
    assert {"semi_active", "pilot_valve", "back_pressure_control"}.issubset(ids)
    assert {"floating_piston", "fail_safe_valve"}.issubset(ids)


def test_taxonomy_path_exposes_engineering_hierarchy():
    taxonomy = TechnologyTaxonomy.default()
    path = taxonomy.path("pilot_valve")
    assert [node.name for node in path] == [
        "Suspension",
        "Semi-active",
        "Pilot Valve",
    ]


def test_classifier_matches_common_damper_poppet_wording():
    classifier = TechnologyClassifier()
    matches = classifier.classify(text="Pressure relief poppet valves for suspension dampers")
    assert any(match.node_id == "blowoff_relief" for match in matches)


def test_classifier_matches_pilot_control_hyphen_variant():
    classifier = TechnologyClassifier()
    matches = classifier.classify(
        text="A suspension damper with a pilot-control valve and proportional solenoid valve"
    )
    assert any(match.node_id == "pilot_valve" for match in matches)
    assert any(match.node_id == "semi_active" for match in matches)


def test_classifier_covers_solenoid_magnetic_architecture():
    classifier = TechnologyClassifier()
    matches = classifier.classify(
        text="Damper electromagnetic actuator magnetic circuit with armature and permanent magnet"
    )
    assert any(match.node_id == "solenoid_actuator" for match in matches)


def test_classifier_covers_digital_valve_and_control_electronics():
    classifier = TechnologyClassifier()
    matches = classifier.classify(
        text=(
            "Suspension damper digital valve with integrated electronic circuit "
            "and printed circuit board"
        )
    )
    ids = {match.node_id for match in matches}
    assert "digital_valve" in ids
    assert "control_electronics" in ids


def test_classifier_splits_underscored_folder_terms():
    classifier = TechnologyClassifier()
    matches = classifier.classify(text="01_电控减振器_CDC_电磁阀")
    ids = {match.node_id for match in matches}
    assert "semi_active" in ids
    assert "cdc_cvsa" in ids


def test_classifier_rejects_generic_non_suspension_valve_and_electronics():
    classifier = TechnologyClassifier()
    matches = classifier.classify(
        text=(
            "A fuel injection system uses a pressure relief valve, electronic control "
            "circuit, permanent magnet actuator and valve body."
        )
    )
    assert matches == ()


def test_classifier_accepts_domain_classification_without_text_anchor():
    classifier = TechnologyClassifier()
    matches = classifier.classify(
        text="Electronic control circuit and valve body",
        classifications=("F16F9/46",),
    )
    assert any(match.node_id == "control_electronics" for match in matches)


def test_classifier_covers_hydraulic_end_stop_wording():
    classifier = TechnologyClassifier()
    matches = classifier.classify(text="Dampers with hydraulic end stops")
    assert any(match.node_id == "travel_control" for match in matches)


def test_classifier_covers_single_axle_roll_control_wording():
    classifier = TechnologyClassifier()
    matches = classifier.classify(
        text="Single axle roll control system with gerotor pump for vehicle suspension"
    )
    assert any(match.node_id == "active_anti_roll" for match in matches)


def test_classifier_rejects_broad_cpc_false_positive_components():
    classifier = TechnologyClassifier()
    matches = classifier.classify(
        text="Pressure relief poppet valve for suspension damper",
        classifications=("F16F9/32AI", "F16F9/34AI"),
    )
    ids = {match.node_id for match in matches}
    assert "blowoff_relief" in ids
    assert not {"hrs", "hcs", "separating_piston"} & ids


def test_classifier_does_not_call_roll_control_a_rebound_spring():
    classifier = TechnologyClassifier()
    matches = classifier.classify(
        text="Single axle roll control system for vehicle suspension",
        classifications=("B60G13/08AI", "B60G21/073AI"),
    )
    ids = {match.node_id for match in matches}
    assert "active_anti_roll" in ids
    assert "rebound_spring" not in ids
