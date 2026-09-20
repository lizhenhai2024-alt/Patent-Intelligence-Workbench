import pytest

from app.core.entity import (
    EntityRelation,
    EntityRelationType,
    include_in_default_group_search,
)


def test_security_interest_is_not_in_default_company_search():
    assert not include_in_default_group_search(EntityRelationType.SECURITY_INTEREST)


def test_acquired_patent_portfolio_is_in_default_company_search():
    assert include_in_default_group_search(EntityRelationType.ACQUIRED_PATENT_PORTFOLIO)


def test_unknown_relation_is_not_in_default_company_search():
    assert not include_in_default_group_search(EntityRelationType.UNKNOWN)


def test_relation_confidence_must_be_bounded():
    with pytest.raises(ValueError):
        EntityRelation(
            source_entity_id="a",
            target_entity_id="b",
            relation_type=EntityRelationType.SAME_ENTITY,
            confidence=1.2,
        )
