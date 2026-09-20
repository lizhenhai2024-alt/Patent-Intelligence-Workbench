import asyncio
from datetime import UTC, date, datetime

from app.core.company_registry import CompanyRegistry
from app.domain.family import FamilyType, PatentFamily, PatentPublication, PriorityClaim
from app.domain.search import SearchHit, SearchPage
from app.providers.base import (
    ProviderCapability,
    ProviderError,
    ProviderInfo,
)
from app.services.family_resolver import FamilyResolver
from app.services.search_service import SearchService
from app.watch.engine import PatentWatchEngine
from app.watch.models import WatchEventType, WatchRule
from app.watch.state import SQLiteWatchStateStore


class MutableSearchProvider:
    info = ProviderInfo(
        name="FAKE_SEARCH",
        capabilities=frozenset({ProviderCapability.SEARCH}),
    )

    def __init__(self):
        self.hits = []
        self.calls = []

    async def lookup_publication(self, publication):
        raise AssertionError("watch should use company search")

    async def search_publications(self, expression, *, page_size=25, page_start=1):
        self.calls.append((expression, page_size, page_start))
        return SearchPage(
            hits=tuple(self.hits),
            total_result_count=len(self.hits),
            range_begin=1 if self.hits else None,
            range_end=len(self.hits) if self.hits else None,
        )


class MutableFamilyProvider:
    info = ProviderInfo(
        name="FAKE_FAMILY",
        capabilities=frozenset({ProviderCapability.FAMILY_SIMPLE}),
    )

    def __init__(self):
        self.families = {}
        self.failures = set()

    async def get_family(self, publication, family_type):
        if publication.canonical in self.failures:
            raise ProviderError("temporary family failure")
        return self.families[publication.canonical]


def _registry():
    return CompanyRegistry.from_dict(
        {
            "companies": [
                {
                    "group_id": "testco",
                    "display_name": "Test Company",
                    "core_watch": True,
                    "entities": [
                        {"name": "Test Company Ltd.", "relation": "SAME_ENTITY"}
                    ],
                }
            ]
        }
    )


def _family(family_id, *members):
    priority = PriorityClaim(
        number=f"JP{family_id}P",
        country="JP",
        priority_date=date(2024, 1, 1),
    )
    return PatentFamily(
        family_type=FamilyType.DOCDB_SIMPLE,
        source="FAKE_FAMILY",
        source_family_id=family_id,
        members=[
            PatentPublication(
                publication_number=number,
                jurisdiction=number[:2],
                publication_date=date(2026, 9, 1),
                priorities=(priority,),
            )
            for number in members
        ],
    )


def _engine(tmp_path, event_sink=None):
    search_provider = MutableSearchProvider()
    family_provider = MutableFamilyProvider()
    search_service = SearchService(
        provider=search_provider,
        company_registry=_registry(),
    )
    store = SQLiteWatchStateStore(tmp_path / "watch.db")
    engine = PatentWatchEngine(
        search_service=search_service,
        family_resolver=FamilyResolver([family_provider]),
        state_store=store,
        event_sink=event_sink,
    )
    return engine, search_provider, family_provider, store


def test_first_run_builds_baseline_then_detects_new_family_member(tmp_path):
    engine, search, families, store = _engine(tmp_path)
    rule = WatchRule(
        rule_id="test-watch",
        name="Test watch",
        company_group="testco",
        technology_terms=("damper",),
    )

    a = "JP2024000123A"
    b = "US20240123456A1"
    search.hits = [
        SearchHit(
            publication_number=a,
            jurisdiction="JP",
            title="Damper A",
            publication_date=date(2026, 9, 1),
        )
    ]
    families.families[a] = _family("F1", a)

    first = asyncio.run(
        engine.run_rule(
            rule,
            now=datetime(2026, 9, 20, 8, 0, tzinfo=UTC),
        )
    )

    assert first.baseline_created is True
    assert first.events == ()
    assert store.publication_seen(rule.rule_id, a)

    search.hits = [
        SearchHit(
            publication_number=b,
            jurisdiction="US",
            title="US family member",
            publication_date=date(2026, 9, 21),
        )
    ]
    families.families[b] = _family("F1", a, b)

    second = asyncio.run(
        engine.run_rule(
            rule,
            now=datetime(2026, 9, 21, 8, 0, tzinfo=UTC),
        )
    )

    assert len(second.events) == 1
    assert second.events[0].event_type is WatchEventType.NEW_FAMILY_MEMBER
    assert second.events[0].publication_number == b
    assert second.events[0].family_source_id == "F1"
    store.close()


def test_after_baseline_new_family_emits_one_family_event(tmp_path):
    engine, search, families, store = _engine(tmp_path)
    rule = WatchRule(
        rule_id="test-watch",
        name="Test watch",
        company_group="testco",
    )
    a = "JP2024000123A"
    c = "EP4000000A1"
    d = "WO2024123456A1"

    search.hits = [SearchHit(a, "JP")]
    families.families[a] = _family("F1", a)
    asyncio.run(
        engine.run_rule(
            rule,
            now=datetime(2026, 9, 20, 8, 0, tzinfo=UTC),
        )
    )

    # Two search hits belong to the same new family. The watch should alert once.
    search.hits = [SearchHit(c, "EP"), SearchHit(d, "WO")]
    family2 = _family("F2", c, d)
    families.families[c] = family2
    families.families[d] = family2

    result = asyncio.run(
        engine.run_rule(
            rule,
            now=datetime(2026, 9, 21, 8, 0, tzinfo=UTC),
        )
    )

    assert len(result.events) == 1
    assert result.events[0].event_type is WatchEventType.NEW_FAMILY
    assert result.events[0].family_source_id == "F2"
    assert store.publication_seen(rule.rule_id, d)
    store.close()


def test_unresolved_publication_is_retried_on_later_run(tmp_path):
    engine, search, families, store = _engine(tmp_path)
    rule = WatchRule(
        rule_id="retry-watch",
        name="Retry family watch",
        company_group="testco",
        notify_on_first_run=True,
    )
    a = "JP2024000123A"
    search.hits = [SearchHit(a, "JP")]
    families.failures.add(a)

    first = asyncio.run(
        engine.run_rule(
            rule,
            now=datetime(2026, 9, 20, 8, 0, tzinfo=UTC),
        )
    )

    assert first.events[0].event_type is WatchEventType.NEW_PUBLICATION_UNRESOLVED_FAMILY
    assert store.publication_seen(rule.rule_id, a)
    assert store.publication_family_key(rule.rule_id, a) is None

    families.failures.clear()
    families.families[a] = _family("F1", a)

    second = asyncio.run(
        engine.run_rule(
            rule,
            now=datetime(2026, 9, 21, 8, 0, tzinfo=UTC),
        )
    )

    assert second.events[0].event_type is WatchEventType.NEW_FAMILY
    assert store.publication_family_key(rule.rule_id, a) is not None
    store.close()


def test_event_sink_archives_events_without_turning_archive_failure_into_rule_failure(tmp_path):
    archived = []

    def sink(rule, event):
        archived.append((rule.rule_id, event.publication_number))
        if event.publication_number.startswith("EP"):
            raise RuntimeError("local archive unavailable")

    engine, search, families, store = _engine(tmp_path, event_sink=sink)
    rule = WatchRule(
        rule_id="archive-watch",
        name="Archive watch",
        company_group="testco",
        notify_on_first_run=True,
    )
    a = "EP4000000A1"
    search.hits = [SearchHit(a, "EP")]
    families.families[a] = _family("F-ARCHIVE", a)

    result = asyncio.run(
        engine.run_rule(
            rule,
            now=datetime(2026, 9, 20, 8, 0, tzinfo=UTC),
        )
    )

    assert archived == [("archive-watch", a)]
    assert len(result.events) == 1
    assert result.events[0].event_type is WatchEventType.NEW_FAMILY
    assert any(error.startswith(f"archive:{a}:") for error in result.errors)
    assert store.get_state(rule.rule_id).last_run_at is not None
    store.close()
