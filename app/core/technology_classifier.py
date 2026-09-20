"""Deterministic evidence-first technology classifier."""

from __future__ import annotations

from dataclasses import dataclass

from .technology_taxonomy import TechnologyNode, TechnologyTaxonomy


@dataclass(frozen=True, slots=True)
class TechnologyMatch:
    node_id: str
    name: str
    score: int
    matched_terms: tuple[str, ...]
    matched_classifications: tuple[str, ...]


class TechnologyClassifier:
    def __init__(self, taxonomy: TechnologyTaxonomy | None = None):
        self.taxonomy = taxonomy or TechnologyTaxonomy.default()

    def classify(
        self,
        *,
        text: str,
        classifications: tuple[str, ...] = (),
        min_score: int = 2,
    ) -> tuple[TechnologyMatch, ...]:
        haystack = text.casefold()
        normalized_classes = tuple(code.upper() for code in classifications)
        matches: list[TechnologyMatch] = []
        for node in self._iter_nodes(self.taxonomy.roots):
            if node.children and not node.search_terms and not node.include_terms:
                continue
            terms = self._candidate_terms(node)
            matched_terms = tuple(term for term in terms if term.casefold() in haystack)
            excluded = any(
                term.casefold() in haystack for term in node.exclude_terms
            )
            if excluded:
                continue
            matched_classes = tuple(
                code for code in node.classifications
                if any(value.startswith(code.upper()) for value in normalized_classes)
            )
            score = len(matched_terms) * 2 + len(matched_classes) * 3
            if score >= min_score:
                matches.append(
                    TechnologyMatch(
                        node_id=node.node_id,
                        name=node.name,
                        score=score,
                        matched_terms=matched_terms,
                        matched_classifications=matched_classes,
                    )
                )
        return tuple(sorted(matches, key=lambda item: (-item.score, item.name)))

    @staticmethod
    def _candidate_terms(node: TechnologyNode) -> tuple[str, ...]:
        return tuple(dict.fromkeys((*node.search_terms, *node.aliases, *node.include_terms)))

    @classmethod
    def _iter_nodes(cls, nodes: tuple[TechnologyNode, ...]):
        for node in nodes:
            yield node
            yield from cls._iter_nodes(node.children)
