"""Incremental company/technology patent monitoring engine."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, date, datetime, timedelta

from app.core.patent_number import PatentNumberError, normalize_patent_number
from app.domain.family import FamilyType, PatentFamily, PatentPublication
from app.domain.search import SearchHit
from app.services.family_resolver import FamilyResolutionError, FamilyResolver
from app.services.search_service import SearchService
from app.watch.family_key import derive_family_key
from app.watch.models import WatchEvent, WatchEventType, WatchRule, WatchRunResult
from app.watch.state import SQLiteWatchStateStore


@dataclass(slots=True)
class PatentWatchEngine:
    search_service: SearchService
    family_resolver: FamilyResolver
    state_store: SQLiteWatchStateStore
    family_type: FamilyType = FamilyType.DOCDB_SIMPLE

    async def run_rule(
        self,
        rule: WatchRule,
        *,
        now: datetime | None = None,
        page_size: int = 100,
        max_pages: int = 10,
    ) -> WatchRunResult:
        started_at = now or datetime.now(UTC)
        if started_at.tzinfo is None:
            raise ValueError("now must be timezone-aware")
        if page_size < 1 or page_size > 100:
            raise ValueError("page_size must be between 1 and 100")
        if max_pages < 1:
            raise ValueError("max_pages must be >= 1")

        self.state_store.upsert_rule(rule)
        state = self.state_store.get_state(rule.rule_id)
        first_run = state.baselined_at is None

        if not rule.enabled:
            return WatchRunResult(
                rule_id=rule.rule_id,
                baseline_created=False,
                searched_hits=0,
                resolved_families=0,
                events=(),
                errors=(),
                started_at=started_at,
                completed_at=started_at,
            )

        if state.last_run_at is not None:
            # One-day overlap protects against source indexing lag while
            # persistent publication de-duplication prevents duplicate alerts.
            published_from = (state.last_run_at - timedelta(days=1)).date()
        else:
            published_from = (started_at - timedelta(days=rule.lookback_days)).date()

        hits = await self._collect_hits(
            rule,
            published_from=published_from,
            published_to=started_at.date(),
            page_size=page_size,
            max_pages=max_pages,
        )

        suppress_events = first_run and not rule.notify_on_first_run
        events: list[WatchEvent] = []
        errors: list[str] = []
        resolved_families = 0

        for hit in hits:
            try:
                normalized = normalize_patent_number(hit.publication_number)
            except PatentNumberError as exc:
                errors.append(f"{hit.publication_number}: {exc}")
                continue

            if self.state_store.publication_seen(rule.rule_id, normalized.canonical):
                existing_family_key = self.state_store.publication_family_key(
                    rule.rule_id,
                    normalized.canonical,
                )
                if existing_family_key is not None:
                    continue
                # Previously unresolved publications are retried so a temporary
                # family-provider failure does not create a permanent orphan.

            try:
                resolution = await self.family_resolver.resolve(
                    normalized,
                    self.family_type,
                )
            except FamilyResolutionError as exc:
                self.state_store.mark_publication(
                    rule.rule_id,
                    normalized.canonical,
                    family_key=None,
                    at=started_at,
                )
                if not suppress_events:
                    events.append(
                        _event_from_hit(
                            rule=rule,
                            hit=hit,
                            publication_number=normalized.canonical,
                            event_type=WatchEventType.NEW_PUBLICATION_UNRESOLVED_FAMILY,
                            family_key=None,
                            family_source_id=None,
                            detected_at=started_at,
                            trigger_publication=normalized.canonical,
                        )
                    )
                errors.append(f"{normalized.canonical}: {exc}")
                continue

            resolved_families += 1
            family = resolution.family
            family_key = derive_family_key(family)
            family_was_seen = self.state_store.family_seen(rule.rule_id, family_key)
            known_members = self.state_store.family_members(rule.rule_id, family_key)
            normalized_members = _normalized_family_members(family)

            if not family_was_seen and not suppress_events:
                events.append(
                    _event_from_hit(
                        rule=rule,
                        hit=hit,
                        publication_number=normalized.canonical,
                        event_type=WatchEventType.NEW_FAMILY,
                        family_key=family_key,
                        family_source_id=family.source_family_id,
                        detected_at=started_at,
                        trigger_publication=normalized.canonical,
                    )
                )
            elif family_was_seen and not suppress_events:
                for member in normalized_members:
                    if member.publication_number in known_members:
                        continue
                    events.append(
                        WatchEvent(
                            event_type=WatchEventType.NEW_FAMILY_MEMBER,
                            rule_id=rule.rule_id,
                            publication_number=member.publication_number,
                            jurisdiction=member.jurisdiction,
                            family_key=family_key,
                            family_source_id=family.source_family_id,
                            title=member.title,
                            publication_date=(
                                member.publication_date.isoformat()
                                if member.publication_date
                                else None
                            ),
                            detected_at=started_at,
                            trigger_publication=normalized.canonical,
                        )
                    )

            self.state_store.mark_family(
                rule.rule_id,
                family_key,
                family_source_id=family.source_family_id,
                at=started_at,
            )
            for member in normalized_members:
                self.state_store.mark_publication(
                    rule.rule_id,
                    member.publication_number,
                    family_key=family_key,
                    at=started_at,
                )
            # Guard against providers whose family payload omits the queried
            # publication itself.
            self.state_store.mark_publication(
                rule.rule_id,
                normalized.canonical,
                family_key=family_key,
                at=started_at,
            )
            self.state_store.commit()

        completed_at = datetime.now(UTC)
        if first_run:
            self.state_store.mark_baselined(rule.rule_id, completed_at)
        self.state_store.mark_run(rule.rule_id, completed_at)

        result = WatchRunResult(
            rule_id=rule.rule_id,
            baseline_created=first_run,
            searched_hits=len(hits),
            resolved_families=resolved_families,
            events=tuple(events),
            errors=tuple(errors),
            started_at=started_at,
            completed_at=completed_at,
        )
        self.state_store.record_run(result)
        return result

    async def _collect_hits(
        self,
        rule: WatchRule,
        *,
        published_from: date,
        published_to: date,
        page_size: int,
        max_pages: int,
    ) -> tuple[SearchHit, ...]:
        hits: list[SearchHit] = []
        seen: set[str] = set()
        page_start = 1

        for _ in range(max_pages):
            response = await self.search_service.search(
                "",
                company=rule.company_group,
                technology_terms=rule.technology_terms,
                jurisdictions=rule.jurisdictions,
                published_from=published_from,
                published_to=published_to,
                page_size=page_size,
                page_start=page_start,
            )
            page = response.page

            for hit in page.hits:
                if hit.publication_number in seen:
                    continue
                seen.add(hit.publication_number)
                hits.append(hit)

            if not page.hits:
                break
            if page.total_result_count is not None and page.range_end is not None:
                if page.range_end >= page.total_result_count:
                    break
            elif len(page.hits) < page_size:
                break

            page_start += page_size

        return tuple(hits)


def _normalized_family_members(family: PatentFamily) -> tuple[PatentPublication, ...]:
    members: list[PatentPublication] = []
    seen: set[str] = set()
    for member in family.members:
        try:
            canonical = normalize_patent_number(member.publication_number).canonical
        except PatentNumberError:
            canonical = member.publication_number
        if canonical in seen:
            continue
        seen.add(canonical)
        members.append(
            PatentPublication(
                publication_number=canonical,
                jurisdiction=member.jurisdiction,
                kind_code=member.kind_code,
                application_number=member.application_number,
                grant_number=member.grant_number,
                title=member.title,
                filing_date=member.filing_date,
                publication_date=member.publication_date,
                grant_date=member.grant_date,
                language=member.language,
                original_assignees=member.original_assignees,
                current_assignees=member.current_assignees,
                priorities=member.priorities,
                classifications=member.classifications,
            )
        )
    return tuple(members)


def _event_from_hit(
    *,
    rule: WatchRule,
    hit: SearchHit,
    publication_number: str,
    event_type: WatchEventType,
    family_key: str | None,
    family_source_id: str | None,
    detected_at: datetime,
    trigger_publication: str,
) -> WatchEvent:
    return WatchEvent(
        event_type=event_type,
        rule_id=rule.rule_id,
        publication_number=publication_number,
        jurisdiction=hit.jurisdiction,
        family_key=family_key,
        family_source_id=family_source_id,
        title=hit.title,
        publication_date=hit.publication_date.isoformat() if hit.publication_date else None,
        detected_at=detected_at,
        trigger_publication=trigger_publication,
    )
