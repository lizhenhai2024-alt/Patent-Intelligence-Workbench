from app.core.technology_taxonomy import TechnologyTaxonomy


def test_passive_damper_contains_valving():
    taxonomy = TechnologyTaxonomy.default()

    suspension = taxonomy.find("suspension")
    passive = taxonomy.find("passive_damper")
    valving = taxonomy.find("valving")

    assert suspension.name == "Suspension"
    assert passive.name == "Passive Damper"
    assert valving.name == "Valving"
    assert any(child.node_id == "passive_damper" for child in suspension.children)
    assert any(child.node_id == "valving" for child in passive.children)


def test_valving_contains_engineering_leaf_nodes_with_search_terms():
    taxonomy = TechnologyTaxonomy.default()
    valving = taxonomy.find("valving")

    expected = {
        "piston_valve",
        "base_valve",
        "disc_stack",
        "rebound_valve",
        "compression_valve",
        "blowoff_relief",
        "check_valve",
        "orifice_bleed",
        "preload_spring",
        "valve_seat_flow",
    }
    assert {child.node_id for child in valving.children} == expected
    assert all(child.search_terms for child in valving.children)
    assert taxonomy.find("base_valve").search_terms == (
        "base valve",
        "foot valve",
        "bottom valve",
    )


def test_semi_active_contains_control_architecture_nodes():
    taxonomy = TechnologyTaxonomy.default()
    semi_active = taxonomy.find("semi_active")

    expected = {
        "cdc_cvsa",
        "pilot_valve",
        "external_solenoid_valve",
        "internal_solenoid_valve",
        "back_pressure_control",
        "floating_piston",
        "fail_safe_valve",
    }
    assert {child.node_id for child in semi_active.children} == expected
    assert all(child.search_terms for child in semi_active.children)
    assert taxonomy.find("pilot_valve").search_terms == (
        "pilot valve",
        "pilot operated valve",
        "pilot controlled damper valve",
    )
