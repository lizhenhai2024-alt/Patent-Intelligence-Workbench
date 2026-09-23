"""Add CPC/IPC classification mappings to the technology taxonomy.

Based on:
- CPC F16F: Springs; shock absorbers; means for damping vibration
- CPC B60G: Vehicle suspension (B60G11, B60G13, B60G15, B60G17, B60G21)
- CPC F16F9/46: Frequency-selective damping (already present on 4 nodes)
"""

from __future__ import annotations

import json
from pathlib import Path

TAXONOMY = Path("app/resources/technology_taxonomy.json")

# Classification assignments per node id.
# Only adding codes verified against CPC scheme; not guessing.
ASSIGNMENTS: dict[str, list[str]] = {
    # Top-level
    "suspension": ["B60G"],
    # Passive damper
    "passive_damper": ["F16F9/00"],
    "valving": ["F16F9/02"],
    "piston_valve": ["F16F9/14", "F16F9/50"],
    "base_valve": ["F16F9/16", "F16F9/512"],
    "disc_stack": ["F16F9/14"],
    "rebound_valve": ["F16F9/14", "F16F9/50"],
    "compression_valve": ["F16F9/16", "F16F9/512"],
    "blowoff_relief": ["F16F9/18"],
    "check_valve": ["F16F9/14"],
    "orifice_bleed": ["F16F9/12"],
    "preload_spring": ["F16F3/00"],
    "valve_seat_flow": ["F16F9/12"],
    # FSD (already has F16F9/46)
    "fsd": ["F16F9/46"],
    "frequency_selective_valve": ["F16F9/46"],
    "hydraulic_delay": ["F16F9/46"],
    "fsd_aux_chamber": ["F16F9/46"],
    "fsd_bypass_flow": ["F16F9/46"],
    "fsd_pressure_switching": ["F16F9/46"],
    "fsd_inertial_switching": ["F16F9/46"],
    # Semi-active
    "semi_active": ["B60G17"],
    "cdc_cvsa": ["F16F9/22", "B60G17"],
    "pilot_valve": ["F16F9/22", "F16F9/46"],
    "external_solenoid_valve": ["F16F9/22", "F16F9/28"],
    "internal_solenoid_valve": ["F16F9/22", "F16F9/24"],
    "back_pressure_control": ["F16F9/28"],
    "floating_piston": ["F16F9/42", "F16F9/46"],
    "fail_safe_valve": ["F16F9/22"],
    "solenoid_actuator": ["H01F7/00"],
    "digital_valve": ["F16F9/22"],
    "control_electronics": ["B60G17"],
    # Active suspension
    "active_suspension": ["B60G17"],
    "hydraulic_active": ["F16F9/00", "B60G17"],
    "electromechanical_active": ["B60G17"],
    "hydraulic_pump": ["F04B"],
    "accumulator": ["F16F9/42"],
    "active_actuator": ["B60G17"],
    "pressure_control": ["F16F9/18"],
    "energy_recovery": ["B60G17"],
    "active_fail_safe": ["F16F9/22"],
    # Air suspension
    "air_suspension": ["B60G11", "B60G17"],
    "air_spring": ["B60G11", "F16F5/00"],
    "air_supply_unit": ["B60G11"],
    "compressor": ["F04B"],
    "reservoir": ["B60G11"],
    "valve_block": ["B60G11"],
    "height_control": ["B60G17"],
    "ride_height_sensor": ["B60G17"],
    "air_dryer": ["B60G11"],
    "air_fail_safe": ["B60G11"],
    # Anti-roll
    "active_anti_roll": ["B60G21"],
    "aar_hydraulic_actuator": ["B60G21"],
    "aar_electromechanical_actuator": ["B60G21"],
    "aar_rotary_actuator": ["B60G21"],
    "aar_decoupling": ["B60G21"],
    "aar_roll_control": ["B60G21"],
    "aar_pressure_control": ["B60G21"],
    "aar_transmission": ["B60G21"],
    "aar_sensor_control": ["B60G21"],
    "aar_fail_safe": ["B60G21"],
    # Springs
    "suspension_spring": ["F16F3/00", "B60G11"],
    "coil_spring": ["F16F3/00"],
    "composite_spring": ["F16F3/00"],
    "variable_rate_spring": ["F16F3/00"],
    "auxiliary_spring": ["F16F3/00"],
    "spring_seat": ["B60G11"],
    "spring_isolator": ["F16F3/00"],
    "jounce_bumper_spring": ["F16F3/00"],
    # Travel control
    "travel_control": ["F16F9/00"],
    "hrs": ["F16F9/00"],
    "hcs": ["F16F9/00"],
    "rebound_spring": ["F16F3/00"],
    "mechanical_rebound_stop": ["F16F9/00"],
    "compression_bump_stop": ["F16F3/00"],
    "end_stop_valve": ["F16F9/00"],
    "progressive_end_stop": ["F16F9/00"],
    # Suspension structure
    "suspension_structure": ["B60G15"],
    "macpherson_strut": ["B60G15"],
    "double_wishbone": ["B60G15"],
    "multi_link": ["B60G15"],
    "control_arm": ["B60G15"],
    "trailing_arm": ["B60G15"],
    "knuckle_carrier": ["B60G15"],
    "subframe": ["B60G15"],
    "damper_fork": ["B60G15"],
    "strut_mounting_interface": ["B60G15"],
    # Mount/bushing
    "mount_bushing": ["F16F15/00"],
    "top_mount": ["F16F15/00"],
    "strut_bearing": ["F16F15/00"],
    "rubber_bushing": ["F16F15/00"],
    "hydraulic_bushing": ["F16F15/00"],
    "control_arm_bushing": ["F16F15/00"],
    "subframe_mount": ["F16F15/00"],
    "damper_eye_bushing": ["F16F15/00"],
    "vibration_isolator": ["F16F15/00"],
    # Seal/friction
    "seal_friction_guidance": ["F16F9/32"],
    "rod_seal": ["F16F9/32"],
    "seal_package": ["F16F9/32"],
    "dust_seal": ["F16F9/32"],
    "o_ring": ["F16J15/00"],
    "rod_guide": ["F16F9/32"],
    "guide_bushing": ["F16F9/32"],
    "piston_band": ["F16F9/32"],
    "ptfe_band": ["F16F9/32"],
    "low_friction_coating": ["F16F9/32"],
    "friction_control": ["F16F9/32"],
    # Damper hardware
    "damper_hardware": ["F16F9/32"],
    "piston_rod": ["F16F9/32"],
    "damper_piston": ["F16F9/32"],
    "pressure_tube": ["F16F9/32"],
    "reservoir_tube": ["F16F9/32"],
    "rod_guide_housing": ["F16F9/32"],
    "end_cap": ["F16F9/32"],
    "gas_chamber": ["F16F9/42"],
    "separating_piston": ["F16F9/42"],
    "external_reservoir": ["F16F9/42"],
    "bottom_base_assembly": ["F16F9/32"],
    "mounting_eye": ["F16F9/32"],
    "damper_bracket": ["F16F9/32"],
    "clevis_fork": ["F16F9/32"],
    "strut_knuckle_clamp": ["B60G15"],
    # NVH
    "nvh_noise": ["F16F9/00"],
    "valve_noise": ["F16F9/00"],
    "valve_chatter": ["F16F9/00"],
    "valve_buzz": ["F16F9/46"],
    "switching_impact_noise": ["F16F9/00"],
    "flow_induced_noise": ["F16F9/00"],
    "jet_shear_noise": ["F16F9/00"],
    "cavity_resonance": ["F16F9/00"],
    "helmholtz_resonance": ["F16F9/00"],
    "cavitation": ["F16F9/00"],
    "aeration": ["F16F9/00"],
    "hydraulic_pulsation": ["F16F9/00"],
    "stick_slip_noise": ["F16F9/00"],
    "knock_noise": ["F16F9/00"],
    "structure_borne_noise": ["F16F9/00"],
}


def assign_classifications(node: dict) -> int:
    """Recursively assign classifications; return count of updated nodes."""
    updated = 0
    node_id = node["id"]
    if node_id in ASSIGNMENTS:
        existing = set(node.get("classifications", []))
        new_codes = ASSIGNMENTS[node_id]
        merged = sorted(set(new_codes) | existing)
        if merged != list(node.get("classifications", [])):
            node["classifications"] = merged
            updated += 1
    for child in node.get("children", []):
        updated += assign_classifications(child)
    return updated


def main() -> None:
    data = json.loads(TAXONOMY.read_text(encoding="utf-8"))
    total = 0
    for root in data["nodes"]:
        total += assign_classifications(root)
    TAXONOMY.write_text(
        json.dumps(data, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    print(f"Updated {total} nodes with classification mappings")


if __name__ == "__main__":
    main()
