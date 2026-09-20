from app.core.company_registry import CompanyRegistry
from app.watch.templates import build_core_company_rules, default_v1_watch_templates


def _registry():
    return CompanyRegistry.from_dict(
        {
            "companies": [
                {
                    "group_id": "a",
                    "display_name": "A",
                    "core_watch": True,
                    "entities": [],
                },
                {
                    "group_id": "b",
                    "display_name": "B",
                    "core_watch": False,
                    "entities": [],
                },
                {
                    "group_id": "clearmotion",
                    "display_name": "ClearMotion",
                    "core_watch": True,
                    "entities": [],
                },
            ]
        }
    )


def test_core_company_templates_only_include_core_watch_groups():
    rules = build_core_company_rules(
        technology_key="damper",
        technology_terms=("减振器",),
        registry=_registry(),
    )

    assert [rule.company_group for rule in rules] == ["a", "clearmotion"]
    assert all(rule.enabled is False for rule in rules)
    assert all(rule.cadence_hours == 24 for rule in rules)


def test_default_templates_include_damper_and_active_suspension():
    rules = default_v1_watch_templates(registry=_registry())

    ids = {rule.rule_id for rule in rules}
    assert "core-a-damper" in ids
    assert "core-clearmotion-damper" in ids
    assert "core-clearmotion-active-suspension" in ids
