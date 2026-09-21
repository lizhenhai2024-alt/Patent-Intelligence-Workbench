from __future__ import annotations

from app.core.company_registry import CompanyRegistry

PAYLOAD = {
    "companies": [
        {
            "group_id": "clearmotion",
            "display_name": "ClearMotion",
            "core_watch": True,
            "entities": [
                {"name": "ClearMotion, Inc.", "relation": "SAME_ENTITY"},
                {
                    "name": "Bose Corporation",
                    "relation": "ACQUIRED_PATENT_PORTFOLIO",
                    "scope": "suspension portfolio only",
                },
            ],
        }
    ]
}


def test_company_only_search_excludes_scoped_acquired_portfolio():
    registry = CompanyRegistry.from_dict(PAYLOAD)
    group = registry.get("ClearMotion")

    assert group.applicant_names() == (
        "ClearMotion, Inc.",
    )


def test_scoped_acquired_portfolio_requires_explicit_include():
    registry = CompanyRegistry.from_dict(PAYLOAD)
    group = registry.get("clearmotion")

    assert group.applicant_names(include_scoped_portfolio=True) == (
        "ClearMotion, Inc.",
        "Bose Corporation",
    )


def test_registry_resolves_legal_entity_alias_to_group():
    registry = CompanyRegistry.from_dict(PAYLOAD)

    assert registry.get("ClearMotion, Inc.").group_id == "clearmotion"
    assert registry.get("ClearMotion").group_id == "clearmotion"


def test_company_portfolio_scope_includes_matching_scoped_entity():
    registry = CompanyRegistry.from_dict(PAYLOAD)
    group = registry.get("clearmotion")

    assert group.applicant_names(portfolio_scope="suspension portfolio") == (
        "ClearMotion, Inc.",
        "Bose Corporation",
    )


def test_lookup_alias_does_not_expand_applicant_names():
    registry = CompanyRegistry.from_dict(
        {
            "companies": [
                {
                    "group_id": "zf",
                    "display_name": "ZF",
                    "core_watch": False,
                    "archive_name": "ZF",
                    "aliases": ["Fichtel_Sachs"],
                    "entities": [
                        {
                            "name": "ZF Friedrichshafen AG",
                            "relation": "SAME_ENTITY",
                        }
                    ],
                }
            ]
        }
    )
    group = registry.get("Fichtel_Sachs")
    assert group.group_id == "zf"
    assert group.applicant_names() == ("ZF Friedrichshafen AG",)


def test_default_registry_resolves_local_library_aliases():
    registry = CompanyRegistry.default()
    assert registry.get("Fichtel_Sachs").group_id == "zf"
    assert registry.get("博格华纳天津").group_id == "borgwarner"
    assert registry.get("BMW").group_id == "bmw"

def test_default_registry_resolves_tenneco_provider_aliases():
    registry = CompanyRegistry.default()
    for alias in (
        "Advanced Suspension Technology Co ltd",
        "Tenneco Automotive Operating Co Inc",
        "Driv Automotive Inc",
        "De Lei Wei Automobile Co ltd",
    ):
        assert registry.get(alias).group_id == "tenneco"
    assert "Driv Automotive Inc" not in registry.get("tenneco").applicant_names()


def test_default_registry_resolves_epo_assignee_aliases():
    registry = CompanyRegistry.default()
    assert registry.get("DREWE AUTOMOTIVE CO LTD").group_id == "tenneco"
    assert registry.get("TIANNAC AUTOMOBILE MAN LIMITED COMPANY").group_id == "tenneco"
    assert registry.get("天纳克汽车经营有限公司").group_id == "tenneco"
    assert registry.get("OEHLINS GROUP AB [SE]").group_id == "ohlins"
