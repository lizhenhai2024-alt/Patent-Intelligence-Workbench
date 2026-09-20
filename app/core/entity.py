"""Company and patent ownership entity-graph primitives."""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum


class EntityRelationType(StrEnum):
    SAME_ENTITY = "SAME_ENTITY"
    PREVIOUS_NAME = "PREVIOUS_NAME"
    CURRENT_NAME = "CURRENT_NAME"
    PARENT_COMPANY = "PARENT_COMPANY"
    SUBSIDIARY = "SUBSIDIARY"
    PREDECESSOR = "PREDECESSOR"
    SUCCESSOR = "SUCCESSOR"
    IP_HOLDING_ENTITY = "IP_HOLDING_ENTITY"
    ACQUIRED_PATENT_PORTFOLIO = "ACQUIRED_PATENT_PORTFOLIO"
    TECHNOLOGY_PREDECESSOR = "TECHNOLOGY_PREDECESSOR"
    ORIGINAL_ASSIGNEE = "ORIGINAL_ASSIGNEE"
    CURRENT_ASSIGNEE = "CURRENT_ASSIGNEE"
    JOINT_APPLICANT = "JOINT_APPLICANT"
    SECURITY_INTEREST = "SECURITY_INTEREST"
    UNKNOWN = "UNKNOWN"


DEFAULT_GROUP_SEARCH_RELATIONS = frozenset(
    {
        EntityRelationType.SAME_ENTITY,
        EntityRelationType.PREVIOUS_NAME,
        EntityRelationType.CURRENT_NAME,
        EntityRelationType.PARENT_COMPANY,
        EntityRelationType.SUBSIDIARY,
        EntityRelationType.PREDECESSOR,
        EntityRelationType.SUCCESSOR,
        EntityRelationType.IP_HOLDING_ENTITY,
        EntityRelationType.ACQUIRED_PATENT_PORTFOLIO,
        EntityRelationType.TECHNOLOGY_PREDECESSOR,
        EntityRelationType.ORIGINAL_ASSIGNEE,
        EntityRelationType.CURRENT_ASSIGNEE,
        EntityRelationType.JOINT_APPLICANT,
    }
)


@dataclass(frozen=True, slots=True)
class CompanyEntity:
    entity_id: str
    canonical_name: str
    country: str | None = None
    entity_type: str = "LEGAL_ENTITY"


@dataclass(frozen=True, slots=True)
class EntityRelation:
    source_entity_id: str
    target_entity_id: str
    relation_type: EntityRelationType
    valid_from: str | None = None
    valid_to: str | None = None
    confidence: float = 1.0
    source_reference: str | None = None
    manual_verified: bool = False

    def __post_init__(self) -> None:
        if not 0.0 <= self.confidence <= 1.0:
            raise ValueError("confidence must be between 0 and 1")


def include_in_default_group_search(relation_type: EntityRelationType) -> bool:
    """Return whether a relation should expand the default company search.

    SECURITY_INTEREST and UNKNOWN are deliberately excluded. This prevents
    financing/collateral entities from being misclassified as technology
    owners merely because they appear in patent assignment history.
    """
    return relation_type in DEFAULT_GROUP_SEARCH_RELATIONS
