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
        "solenoid_actuator",
        "digital_valve",
        "control_electronics",
    }
    assert {child.node_id for child in semi_active.children} == expected
    assert all(child.search_terms for child in semi_active.children)
    pilot_terms = taxonomy.find("pilot_valve").search_terms
    assert {
        "pilot valve",
        "pilot operated valve",
        "pilot controlled damper valve",
        "pilot-control valve",
        "pilot control valve",
        "pilot chamber",
    }.issubset(set(pilot_terms))


def test_active_suspension_contains_core_architecture_nodes():
    taxonomy = TechnologyTaxonomy.default()
    active = taxonomy.find("active_suspension")

    expected = {
        "hydraulic_active",
        "electromechanical_active",
        "hydraulic_pump",
        "accumulator",
        "active_actuator",
        "pressure_control",
        "energy_recovery",
        "active_fail_safe",
    }
    assert {child.node_id for child in active.children} == expected
    assert all(child.search_terms for child in active.children)
    assert taxonomy.find("accumulator").search_terms == (
        "suspension accumulator",
        "hydraulic accumulator suspension",
        "active suspension accumulator",
    )


def test_air_suspension_contains_core_system_nodes():
    taxonomy = TechnologyTaxonomy.default()
    air = taxonomy.find("air_suspension")

    expected = {
        "air_spring",
        "air_supply_unit",
        "compressor",
        "reservoir",
        "valve_block",
        "height_control",
        "ride_height_sensor",
        "air_dryer",
        "air_fail_safe",
    }
    assert {child.node_id for child in air.children} == expected
    assert all(child.search_terms for child in air.children)
    assert taxonomy.find("valve_block").search_terms == (
        "air suspension valve block",
        "pneumatic valve manifold suspension",
        "air distribution valve suspension",
    )


def test_active_anti_roll_contains_core_architecture_nodes():
    taxonomy = TechnologyTaxonomy.default()
    active_anti_roll = taxonomy.find("active_anti_roll")

    expected = {
        "aar_hydraulic_actuator",
        "aar_electromechanical_actuator",
        "aar_rotary_actuator",
        "aar_decoupling",
        "aar_roll_control",
        "aar_pressure_control",
        "aar_transmission",
        "aar_sensor_control",
        "aar_fail_safe",
    }
    assert {child.node_id for child in active_anti_roll.children} == expected
    assert all(child.search_terms for child in active_anti_roll.children)
    assert taxonomy.find("aar_decoupling").search_terms == (
        "stabilizer decoupling",
        "anti roll bar disconnect",
        "active stabilizer clutch",
    )


def test_extended_suspension_taxonomy_core_nodes():
    taxonomy = TechnologyTaxonomy.default()
    suspension = taxonomy.find("suspension")
    child_ids = {child.node_id for child in suspension.children}
    expected = {
        "suspension_spring",
        "travel_control",
        "suspension_structure",
        "mount_bushing",
        "seal_friction_guidance",
        "damper_hardware",
        "nvh_noise",
        "materials_manufacturing",
    }
    assert expected.issubset(child_ids)

    assert taxonomy.find("spring_seat").search_terms == (
        "spring seat",
        "suspension spring seat",
        "coil spring seat",
        "upper spring seat",
        "lower spring seat",
        "spring perch",
    )
    assert "Leaf Spring" not in {n.name for n in taxonomy.find("suspension_spring").children}
    assert "Torsion Bar" not in {n.name for n in taxonomy.find("suspension_spring").children}


def test_travel_control_and_fsd_are_structured():
    taxonomy = TechnologyTaxonomy.default()
    travel = taxonomy.find("travel_control")
    assert "rebound_spring" in {child.node_id for child in travel.children}
    assert taxonomy.find("rebound_spring").search_terms[0] == "rebound spring"

    fsd = taxonomy.find("fsd")
    assert fsd.name == "FSD / Frequency Selective Damping"
    assert {child.node_id for child in fsd.children} == {
        "frequency_selective_valve",
        "hydraulic_delay",
        "fsd_aux_chamber",
        "fsd_bypass_flow",
        "fsd_pressure_switching",
        "fsd_inertial_switching",
    }


def test_separating_and_control_floating_pistons_remain_distinct():
    taxonomy = TechnologyTaxonomy.default()
    assert taxonomy.find("separating_piston").name == "Separating Piston"
    assert taxonomy.find("floating_piston").name == "Floating Piston"
    assert taxonomy.find("separating_piston").node_id != taxonomy.find("floating_piston").node_id
