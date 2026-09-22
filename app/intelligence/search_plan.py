"""Inspectable engineering-problem search preparation."""

from __future__ import annotations

from dataclasses import dataclass

from app.core.technology_dictionary import TechnologyDictionary


@dataclass(frozen=True, slots=True)
class SearchTermGroup:
    topic_id: str
    topic_name: str
    terms: tuple[str, ...]
    source: str


@dataclass(frozen=True, slots=True)
class SearchPlan:
    problem: str
    groups: tuple[SearchTermGroup, ...]
    unmatched: bool

    @property
    def editable_query(self) -> str:
        # A human selects and edits these terms before triggering the existing search.
        return " ".join(self.groups[0].terms[:2]) if self.groups else self.problem


def plan_search(problem: str, dictionary: TechnologyDictionary | None = None) -> SearchPlan:
    text = problem.strip()
    if not text:
        raise ValueError("请描述工程问题")
    source = dictionary or TechnologyDictionary.default()
    groups = []
    for topic in source.topics:
        if not topic.matches(text):
            continue
        terms = tuple(
            dict.fromkeys(
                term.strip() for values in topic.aliases.values() for term in values if term.strip()
            )
        )
        if terms:
            groups.append(
                SearchTermGroup(topic.topic_id, topic.display_name, terms, "内置技术词典")
            )
    return SearchPlan(text, tuple(groups), not bool(groups))
