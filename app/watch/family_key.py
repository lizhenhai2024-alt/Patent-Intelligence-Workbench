"""Derive deterministic keys for family de-duplication in Patent Watch."""

from __future__ import annotations

import hashlib

from app.domain.family import PatentFamily


def derive_family_key(family: PatentFamily) -> str:
    if family.source_family_id:
        return f"{family.family_type.value}:{family.source}:{family.source_family_id}"

    earliest = family.earliest_priority
    if earliest is not None:
        return (
            f"{family.family_type.value}:PRIORITY:"
            f"{earliest.number}:{earliest.priority_date or ''}"
        )

    members = "|".join(sorted(family.member_numbers()))
    digest = hashlib.sha256(members.encode("utf-8")).hexdigest()[:24]
    return f"{family.family_type.value}:MEMBERS:{digest}"
