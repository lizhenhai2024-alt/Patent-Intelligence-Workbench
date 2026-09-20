"""Default Patent Watch templates for core damper competitors."""

from __future__ import annotations

import re

from app.core.company_registry import CompanyRegistry
from app.watch.models import WatchRule
from app.watch.state import SQLiteWatchStateStore

_ID_SAFE = re.compile(r"[^a-z0-9]+")


def build_core_company_rules(
    *,
    technology_key: str,
    technology_terms: tuple[str, ...],
    registry: CompanyRegistry | None = None,
    cadence_hours: int = 24,
    enabled: bool = False,
) -> tuple[WatchRule, ...]:
    """Create one saved-rule template per core monitored company.

    Templates are disabled by default so first application launch does not
    unexpectedly issue many external API requests. The UI can enable selected
    rules or all rules explicitly.
    """
    company_registry = registry or CompanyRegistry.default()
    key = _safe_id(technology_key)
    label = technology_terms[0] if technology_terms else technology_key

    return tuple(
        WatchRule(
            rule_id=f"core-{group.group_id}-{key}",
            name=f"{group.display_name} · {label}",
            company_group=group.group_id,
            technology_terms=technology_terms,
            cadence_hours=cadence_hours,
            enabled=enabled,
        )
        for group in company_registry.groups
        if group.core_watch
    )


def default_v1_watch_templates(
    registry: CompanyRegistry | None = None,
) -> tuple[WatchRule, ...]:
    company_registry = registry or CompanyRegistry.default()

    damper_rules = build_core_company_rules(
        technology_key="damper",
        technology_terms=("减振器",),
        registry=company_registry,
    )

    active_groups = {
        "astemo",
        "kyb",
        "tenneco",
        "zf",
        "bwi",
        "hl_mando",
        "bilstein",
        "clearmotion",
    }
    active_rules = tuple(
        WatchRule(
            rule_id=f"core-{group.group_id}-active-suspension",
            name=f"{group.display_name} · 主动悬架",
            company_group=group.group_id,
            technology_terms=("主动悬架",),
            enabled=False,
            cadence_hours=24,
        )
        for group in company_registry.groups
        if group.group_id in active_groups
    )

    return damper_rules + active_rules


def seed_watch_templates(
    store: SQLiteWatchStateStore,
    rules: tuple[WatchRule, ...],
) -> int:
    """Insert/update templates and return the number of processed rules."""
    for rule in rules:
        store.upsert_rule(rule)
    return len(rules)


def _safe_id(value: str) -> str:
    normalized = _ID_SAFE.sub("-", value.casefold()).strip("-")
    return normalized or "topic"

