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
