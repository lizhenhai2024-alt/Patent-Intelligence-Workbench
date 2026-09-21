"""Deterministic evidence-first technology classifier."""

from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass

from .technology_taxonomy import TechnologyNode, TechnologyTaxonomy

_DOMAIN_TEXT_TERMS = (
    "damper",
    "shock absorber",
    "suspension",
    "strut",
    "air spring",
    "anti roll",
    "stabilizer bar",
    "stabiliser bar",
    "ride height",
    "rebound stop",
    "compression stop",
    "减振器",
    "减震器",
    "悬架",
    "空气弹簧",
    "稳定杆",
    "防倾杆",
    "复原缓冲",
    "压缩缓冲",
    "阻尼力",
)
_DOMAIN_CLASS_PREFIXES = ("B60G", "F16F9")


def _normalize_text(value: str) -> str:
    normalized = unicodedata.normalize("NFKC", value).casefold()
    normalized = normalized.replace("_", " ")
    normalized = re.sub(r"[^\w]+", " ", normalized, flags=re.UNICODE)
    return " ".join(normalized.split())


# The domain gate runs for every classified document, so the normalized form of
# these constant terms is computed once at import time instead of per call.
_NORMALIZED_DOMAIN_TERMS: tuple[str, ...] = tuple(
    _normalize_text(term) for term in _DOMAIN_TEXT_TERMS
)


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
        # Taxonomy nodes are static, so their normalized search terms are
        # cached per node id instead of being re-normalized for every document.
        self._term_cache: dict[str, tuple[tuple[str, str], ...]] = {}
        self._exclude_cache: dict[str, tuple[str, ...]] = {}

    def classify(
        self,
        *,
        text: str,
        classifications: tuple[str, ...] = (),
        min_score: int = 2,
        require_domain_context: bool = True,
    ) -> tuple[TechnologyMatch, ...]:
        haystack = _normalize_text(text)
        normalized_classes = tuple(code.upper() for code in classifications)
        if require_domain_context and not self._has_domain_context(
            haystack,
            normalized_classes,
        ):
            return ()
        matches: list[TechnologyMatch] = []
        for node in self._iter_nodes(self.taxonomy.roots):
            if node.children and not node.search_terms and not node.include_terms:
                continue
            candidates = self._normalized_terms(node)
            matched_terms = tuple(
                original for original, normalized in candidates if normalized in haystack
            )
            excluded = any(term in haystack for term in self._normalized_excludes(node))
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

    def _normalized_terms(self, node: TechnologyNode) -> tuple[tuple[str, str], ...]:
        cached = self._term_cache.get(node.node_id)
        if cached is None:
            cached = tuple(
                (term, _normalize_text(term)) for term in self._candidate_terms(node)
            )
            self._term_cache[node.node_id] = cached
        return cached

    def _normalized_excludes(self, node: TechnologyNode) -> tuple[str, ...]:
        cached = self._exclude_cache.get(node.node_id)
        if cached is None:
            cached = tuple(_normalize_text(term) for term in node.exclude_terms)
            self._exclude_cache[node.node_id] = cached
        return cached

    @staticmethod
    def _normalize_text(value: str) -> str:
        return _normalize_text(value)

    @staticmethod
    def _has_domain_context(
        haystack: str,
        classifications: tuple[str, ...],
    ) -> bool:
        if any(
            value.startswith(prefix)
            for value in classifications
            for prefix in _DOMAIN_CLASS_PREFIXES
        ):
            return True
        return any(term in haystack for term in _NORMALIZED_DOMAIN_TERMS)

    @staticmethod
    def _candidate_terms(node: TechnologyNode) -> tuple[str, ...]:
        return tuple(dict.fromkeys((*node.search_terms, *node.aliases, *node.include_terms)))

    @classmethod
    def _iter_nodes(cls, nodes: tuple[TechnologyNode, ...]):
        for node in nodes:
            yield node
            yield from cls._iter_nodes(node.children)
