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

    assert group.applicant_names(technology_context=False) == (
        "ClearMotion, Inc.",
    )


def test_company_technology_search_includes_scoped_acquired_portfolio():
    registry = CompanyRegistry.from_dict(PAYLOAD)
    group = registry.get("clearmotion")

    assert group.applicant_names(technology_context=True) == (
        "ClearMotion, Inc.",
        "Bose Corporation",
    )
