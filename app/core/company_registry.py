"""Load company groups and expand safe applicant names for search."""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path

from app.core.entity import EntityRelationType, include_in_default_group_search


@dataclass(frozen=True, slots=True)
class RegisteredEntity:
    name: str
    relation: EntityRelationType
    scope: str | None = None


@dataclass(frozen=True, slots=True)
class CompanyGroup:
    group_id: str
    display_name: str
    core_watch: bool
    entities: tuple[RegisteredEntity, ...]

    def applicant_names(self, *, technology_context: bool) -> tuple[str, ...]:
        names: list[str] = []
        for entity in self.entities:
            if not include_in_default_group_search(entity.relation):
                continue
            if entity.scope and not technology_context:
                continue
            if entity.name not in names:
                names.append(entity.name)
        if not names:
            names.append(self.display_name)
        return tuple(names)


class CompanyRegistry:
    def __init__(self, groups: tuple[CompanyGroup, ...]):
        self.groups = groups

    @classmethod
    def from_dict(cls, payload: dict) -> CompanyRegistry:
        groups: list[CompanyGroup] = []
        for item in payload.get("companies", []):
            entities = tuple(
                RegisteredEntity(
                    name=entity["name"],
                    relation=EntityRelationType(entity["relation"]),
                    scope=entity.get("scope"),
                )
                for entity in item.get("entities", [])
            )
            groups.append(
                CompanyGroup(
                    group_id=item["group_id"],
                    display_name=item["display_name"],
                    core_watch=bool(item.get("core_watch", False)),
                    entities=entities,
                )
            )
        return cls(tuple(groups))

    @classmethod
    def from_json_file(cls, path: str | Path) -> CompanyRegistry:
        payload = json.loads(Path(path).read_text(encoding="utf-8"))
        return cls.from_dict(payload)

    @classmethod
    def default(cls) -> CompanyRegistry:
        root = Path(__file__).resolve().parents[2]
        return cls.from_json_file(root / "data" / "companies" / "core_companies.json")

    def get(self, value: str) -> CompanyGroup:
        needle = _normalize_company_key(value)
        for group in self.groups:
            if _normalize_company_key(group.group_id) == needle:
                return group
            if _normalize_company_key(group.display_name) == needle:
                return group
        raise KeyError(f"Unknown company group: {value}")


def _normalize_company_key(value: str) -> str:
    return "".join(ch for ch in value.casefold() if ch.isalnum())
