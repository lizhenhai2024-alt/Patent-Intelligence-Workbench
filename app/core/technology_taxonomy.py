"""Hierarchical engineering taxonomy for suspension patent intelligence."""

from __future__ import annotations

import json
from dataclasses import dataclass
from importlib import resources


@dataclass(frozen=True, slots=True)
class TechnologyNode:
    node_id: str
    name: str
    children: tuple[TechnologyNode, ...] = ()


class TechnologyTaxonomy:
    def __init__(self, roots: tuple[TechnologyNode, ...]):
        self.roots = roots

    @classmethod
    def from_dict(cls, payload: dict) -> TechnologyTaxonomy:
        def build(item: dict) -> TechnologyNode:
            return TechnologyNode(
                node_id=item["id"],
                name=item["name"],
                children=tuple(build(child) for child in item.get("children", [])),
            )
        return cls(tuple(build(item) for item in payload.get("nodes", [])))

    @classmethod
    def default(cls) -> TechnologyTaxonomy:
        text = (
            resources.files("app.resources")
            .joinpath("technology_taxonomy.json")
            .read_text(encoding="utf-8")
        )
        return cls.from_dict(json.loads(text))

    def find(self, node_id: str) -> TechnologyNode:
        def walk(nodes: tuple[TechnologyNode, ...]) -> TechnologyNode | None:
            for node in nodes:
                if node.node_id == node_id:
                    return node
                found = walk(node.children)
                if found is not None:
                    return found
            return None

        result = walk(self.roots)
        if result is None:
            raise KeyError(node_id)
        return result
