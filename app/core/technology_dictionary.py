"""Multilingual technology dictionary used to expand engineering search terms."""

from __future__ import annotations

import json
from dataclasses import dataclass
from importlib import resources


@dataclass(frozen=True, slots=True)
class TechnologyTopic:
    topic_id: str
    display_name: str
    aliases: dict[str, tuple[str, ...]]
    provider_terms: dict[str, tuple[str, ...]]

    def matches(self, text: str) -> bool:
        needle = _normalize_match_text(text)
        if not needle:
            return False
        for values in self.aliases.values():
            for alias in values:
                normalized_alias = _normalize_match_text(alias)
                if normalized_alias and normalized_alias in needle:
                    return True
        return False

    def terms_for(self, provider_name: str) -> tuple[str, ...]:
        return (
            self.provider_terms.get(provider_name)
            or self.provider_terms.get("DEFAULT")
            or ()
        )


class TechnologyDictionary:
    def __init__(self, topics: tuple[TechnologyTopic, ...]):
        self.topics = topics

    @classmethod
    def from_dict(cls, payload: dict) -> TechnologyDictionary:
        topics: list[TechnologyTopic] = []
        for item in payload.get("topics", []):
            aliases = {
                language: tuple(values)
                for language, values in item.get("aliases", {}).items()
            }
            provider_terms = {
                provider: tuple(values)
                for provider, values in item.get("provider_terms", {}).items()
            }
            topics.append(
                TechnologyTopic(
                    topic_id=item["topic_id"],
                    display_name=item["display_name"],
                    aliases=aliases,
                    provider_terms=provider_terms,
                )
            )
        return cls(tuple(topics))

    @classmethod
    def default(cls) -> TechnologyDictionary:
        text = (
            resources.files("app.resources")
            .joinpath("core_topics.json")
            .read_text(encoding="utf-8")
        )
        return cls.from_dict(json.loads(text))

    def expand(self, text: str, *, provider_name: str) -> tuple[tuple[str, ...], ...]:
        groups: list[tuple[str, ...]] = []
        seen_topics: set[str] = set()

        for topic in self.topics:
            if topic.topic_id in seen_topics or not topic.matches(text):
                continue
            terms = _dedupe(topic.terms_for(provider_name))
            if terms:
                groups.append(terms)
                seen_topics.add(topic.topic_id)

        return tuple(groups)


def _normalize_match_text(value: str) -> str:
    return "".join(ch for ch in value.casefold() if ch.isalnum())


def _dedupe(values: tuple[str, ...]) -> tuple[str, ...]:
    result: list[str] = []
    for value in values:
        normalized = " ".join(value.split())
        if normalized and normalized not in result:
            result.append(normalized)
    return tuple(result)
