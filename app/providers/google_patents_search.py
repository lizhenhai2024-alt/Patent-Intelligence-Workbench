"""Zero-credential Google Patents search and simple-family provider.

Uses the public structured query response and structured itemprop metadata
from individual patent pages. No browser automation or visual DOM scraping is
used.
"""

from __future__ import annotations

import asyncio
import html
import re
from dataclasses import dataclass
from datetime import date
from html.parser import HTMLParser
from urllib.parse import urlencode

import httpx

from app.core.patent_number import PatentNumber, PatentNumberError, normalize_patent_number
from app.domain.family import FamilyType, PatentFamily, PatentPublication
from app.domain.reader import PatentReaderDocument
from app.domain.search import SearchExpression, SearchHit, SearchPage
from app.providers.base import (
    ProviderCapability,
    ProviderInfo,
    ProviderRateLimitError,
    ProviderResponseError,
    ProviderUnavailableError,
)

GOOGLE_QUERY_URL = "https://patents.google.com/xhr/query"
GOOGLE_PATENT_URL = "https://patents.google.com/patent"
USER_AGENT = "Patent-Intelligence-Workbench/1.0"

_MARKUP_RE = re.compile(r"<[^>]+>")
_KIND_RE = re.compile(r"([A-Z]{1,2}\d{0,2})$")


class _PatentPageParser(HTMLParser):
    _TEXT_PROPS = {
        "title",
        "publicationNumber",
        "applicationNumber",
        "assigneeCurrent",
        "assigneeOriginal",
        "countryCode",
        "kindCode",
        "publicationDate",
        "filingDate",
        "grantDate",
        "abstract",
        "classificationCpc",
        "classificationIpc",
    }

    def __init__(self) -> None:
        super().__init__()
        self.values: dict[str, list[str]] = {}
        self.named_meta: dict[str, list[str]] = {}
        self.family_members: list[tuple[str, str | None]] = []
        self.sections: dict[str, list[str]] = {"claims": [], "description": []}
        self._captures: list[dict[str, object]] = []
        self._section_stack: list[tuple[str, str]] = []
        self._in_docdb_family = False
        self._family_current: dict[str, str] = {}

    def handle_starttag(
        self,
        tag: str,
        attrs: list[tuple[str, str | None]],
    ) -> None:
        values = {key: value for key, value in attrs}
        itemprop = values.get("itemprop")

        if tag == "tr" and itemprop == "docdbFamily":
            self._in_docdb_family = True
            self._family_current = {}

        if itemprop in self.sections:
            self._section_stack.append((tag, itemprop))

        if self._section_stack and tag in {"p", "div", "li"}:
            self._captures.append(
                {
                    "tag": tag,
                    "prop": f"__section__:{self._section_stack[-1][1]}",
                    "data": [],
                    "family": False,
                }
            )

        if tag == "meta":
            content = values.get("content")
            if itemprop and content:
                self._store(itemprop, content)
            name = values.get("name")
            if name and content:
                self.named_meta.setdefault(name, []).append(content)
            return

        if itemprop in self._TEXT_PROPS:
            datetime_value = values.get("datetime")
            if tag == "time" and datetime_value:
                self._store(itemprop, datetime_value)
                return
            self._captures.append(
                {
                    "tag": tag,
                    "prop": itemprop,
                    "data": [],
                    "family": self._in_docdb_family,
                }
            )

    def handle_data(self, data: str) -> None:
        if self._captures:
            capture = self._captures[-1]
            buffer = capture["data"]
            assert isinstance(buffer, list)
            buffer.append(data)

    def handle_endtag(self, tag: str) -> None:
        for index in range(len(self._captures) - 1, -1, -1):
            capture = self._captures[index]
            if capture["tag"] != tag:
                continue
            self._captures.pop(index)
            buffer = capture["data"]
            assert isinstance(buffer, list)
            text = _clean_text("".join(str(item) for item in buffer))
            if text:
                prop = str(capture["prop"])
                if prop.startswith("__section__:"):
                    section = prop.split(":", 1)[1]
                    self.sections.setdefault(section, []).append(text)
                else:
                    family = bool(capture["family"])
                    self._store(prop, text, family=family)
            break

        if self._section_stack and tag == self._section_stack[-1][0]:
            self._section_stack.pop()

        if tag == "tr" and self._in_docdb_family:
            publication = self._family_current.get("publicationNumber")
            if publication:
                self.family_members.append(
                    (
                        publication,
                        self._family_current.get("publicationDate"),
                    )
                )
            self._family_current = {}
            self._in_docdb_family = False

    def _store(
        self,
        prop: str,
        value: str,
        *,
        family: bool | None = None,
    ) -> None:
        is_family = self._in_docdb_family if family is None else family
        if is_family:
            self._family_current[prop] = value
            return
        self.values.setdefault(prop, []).append(value)


def _clean_text(value: str | None) -> str:
    if not value:
        return ""
    return " ".join(html.unescape(_MARKUP_RE.sub("", value)).split())


def _first(values: dict[str, list[str]], key: str) -> str | None:
    items = values.get(key, [])
    return items[0] if items else None


def _parse_date(value: str | None) -> date | None:
    if not value:
        return None
    try:
        return date.fromisoformat(value[:10])
    except ValueError:
        return None


def _identity(publication_number: str) -> tuple[str, str | None, str]:
    clean = publication_number.strip().upper().replace(" ", "")
    try:
        normalized = normalize_patent_number(clean)
        return (
            normalized.jurisdiction,
            normalized.kind_code,
            normalized.canonical,
        )
    except PatentNumberError:
        jurisdiction = clean[:2] if len(clean) >= 2 else ""
        kind_match = _KIND_RE.search(clean[2:])
        kind = kind_match.group(1) if kind_match else None
        return jurisdiction, kind, clean


def _quoted_term(value: str) -> str:
    normalized = " ".join(value.split()).replace('"', "")
    return f'"{normalized}"' if " " in normalized else normalized


def _expression_text(expression: SearchExpression) -> str:
    parts: list[str] = []
    if expression.text_terms:
        terms = " OR ".join(_quoted_term(term) for term in expression.text_terms)
        parts.append(f"({terms})" if len(expression.text_terms) > 1 else terms)

    for group in expression.text_groups:
        if not group:
            continue
        terms = " OR ".join(_quoted_term(term) for term in group)
        parts.append(f"({terms})" if len(group) > 1 else terms)
    return " ".join(parts)


def _search_hit_from_json(payload: dict) -> SearchHit | None:
    publication_number = str(payload.get("publication_number") or "").strip()
    if not publication_number:
        return None
    jurisdiction, kind, canonical = _identity(publication_number)
    assignee = _clean_text(str(payload.get("assignee") or ""))
    return SearchHit(
        publication_number=canonical,
        jurisdiction=jurisdiction,
        kind_code=kind,
        title=_clean_text(str(payload.get("title") or "")) or None,
        applicants=(assignee,) if assignee else (),
        publication_date=_parse_date(str(payload.get("publication_date") or "")),
        source="GOOGLE_PATENTS",
    )


def _page_hit(parser: _PatentPageParser, requested: PatentNumber) -> SearchHit:
    publication_number = _first(parser.values, "publicationNumber")
    canonical = publication_number or requested.canonical
    jurisdiction, kind, canonical = _identity(canonical)
    applicants = tuple(
        dict.fromkeys(
            parser.values.get("assigneeCurrent", [])
            or parser.values.get("assigneeOriginal", [])
        )
    )
    classifications = tuple(
        dict.fromkeys(
            parser.values.get("classificationCpc", [])
            + parser.values.get("classificationIpc", [])
        )
    )
    return SearchHit(
        publication_number=canonical,
        jurisdiction=jurisdiction,
        kind_code=kind,
        title=_first(parser.values, "title"),
        abstract=_first(parser.values, "abstract"),
        applicants=applicants,
        classifications=classifications,
        publication_date=_parse_date(_first(parser.values, "publicationDate")),
        source="GOOGLE_PATENTS",
    )


@dataclass(slots=True)
class GooglePatentsSearchProvider:
    timeout_seconds: float = 30.0
    user_agent: str = USER_AGENT
    max_attempts: int = 3
    retry_delay_seconds: float = 1.0

    info = ProviderInfo(
        name="GOOGLE_PATENTS",
        capabilities=frozenset(
            {
                ProviderCapability.SEARCH,
                ProviderCapability.PUBLICATION_LOOKUP,
                ProviderCapability.FAMILY_SIMPLE,
                ProviderCapability.BIBLIOGRAPHY,
            }
        ),
    )

    async def lookup_publication(self, publication: PatentNumber) -> SearchPage:
        url = f"{GOOGLE_PATENT_URL}/{publication.canonical}/en"
        async with httpx.AsyncClient(
            timeout=self.timeout_seconds,
            follow_redirects=True,
            headers={"User-Agent": self.user_agent},
        ) as client:
            response = await self._get(client, url, allow_not_found=True)
            if response is None:
                return SearchPage(hits=(), total_result_count=0)
            parser = _PatentPageParser()
            parser.feed(response.text)
            hit = _page_hit(parser, publication)
            return SearchPage(
                hits=(hit,),
                total_result_count=1,
                range_begin=1,
                range_end=1,
            )

    async def get_reader_document(
        self,
        publication: PatentNumber,
    ) -> PatentReaderDocument:
        url = f"{GOOGLE_PATENT_URL}/{publication.canonical}/en"
        async with httpx.AsyncClient(
            timeout=self.timeout_seconds,
            follow_redirects=True,
            headers={"User-Agent": self.user_agent},
        ) as client:
            response = await self._get(client, url, allow_not_found=True)
            if response is None:
                raise ProviderResponseError(
                    f"Google Patents did not find {publication.canonical}."
                )
        parser = _PatentPageParser()
        parser.feed(response.text)
        hit = _page_hit(parser, publication)
        return PatentReaderDocument(
            publication_number=hit.publication_number,
            title=hit.title,
            abstract=hit.abstract,
            claims="\n\n".join(parser.sections.get("claims", ())),
            description="\n\n".join(parser.sections.get("description", ())),
            classifications=hit.classifications,
        )

    async def search_publications(
        self,
        expression: SearchExpression,
        *,
        page_size: int = 25,
        page_start: int = 1,
    ) -> SearchPage:
        if page_size < 1 or page_size > 100:
            raise ValueError("page_size must be between 1 and 100")
        if page_start < 1:
            raise ValueError("page_start must be >= 1")

        applicants: tuple[str | None, ...] = expression.applicants or (None,)
        text_query = _expression_text(expression)
        hits: list[SearchHit] = []
        seen: set[str] = set()
        total_count = 0
        allowed = {value.upper() for value in expression.jurisdictions}
        remote_page = (page_start - 1) // 100
        local_offset = (page_start - 1) % 100

        async with httpx.AsyncClient(
            timeout=self.timeout_seconds,
            follow_redirects=True,
            headers={"User-Agent": self.user_agent},
        ) as client:
            for applicant in applicants:
                query_hits, query_total = await self._query_results(
                    client,
                    text_query=text_query,
                    applicant=applicant,
                    expression=expression,
                    page=remote_page,
                )
                total_count += query_total
                for hit in query_hits:
                    if allowed and hit.jurisdiction.upper() not in allowed:
                        continue
                    if expression.published_from and hit.publication_date:
                        if hit.publication_date < expression.published_from:
                            continue
                    if expression.published_to and hit.publication_date:
                        if hit.publication_date > expression.published_to:
                            continue
                    if hit.publication_number in seen:
                        continue
                    seen.add(hit.publication_number)
                    hits.append(hit)
                if len(hits) >= local_offset + page_size:
                    break

        page_hits = hits[local_offset : local_offset + page_size]
        return SearchPage(
            hits=tuple(page_hits),
            total_result_count=total_count or len(hits),
            range_begin=page_start if page_hits else None,
            range_end=page_start + len(page_hits) - 1 if page_hits else None,
        )

    async def _query_results(
        self,
        client: httpx.AsyncClient,
        *,
        text_query: str,
        applicant: str | None,
        expression: SearchExpression,
        page: int,
    ) -> tuple[tuple[SearchHit, ...], int]:
        params: list[tuple[str, str]] = []
        if text_query:
            params.append(("q", text_query))
        if applicant:
            params.append(("assignee", applicant))
        if len(expression.jurisdictions) == 1:
            params.append(("country", expression.jurisdictions[0].upper()))
        if expression.published_from:
            params.append(
                ("after", f"publication:{expression.published_from:%Y%m%d}")
            )
        if expression.published_to:
            params.append(
                ("before", f"publication:{expression.published_to:%Y%m%d}")
            )
        params.append(("num", "100"))
        if page:
            params.append(("page", str(page)))

        inner_query = urlencode(params)
        response = await self._get(
            client,
            GOOGLE_QUERY_URL,
            params={"url": inner_query, "exp": ""},
        )
        assert response is not None
        try:
            payload = response.json()
        except ValueError as exc:
            raise ProviderResponseError(
                "Google Patents structured search returned invalid JSON."
            ) from exc

        results = payload.get("results") or {}
        total = int(results.get("total_num_results") or 0)
        parsed: list[SearchHit] = []
        for cluster in results.get("cluster") or []:
            for item in cluster.get("result") or []:
                patent = item.get("patent") or {}
                hit = _search_hit_from_json(patent)
                if hit is not None:
                    parsed.append(hit)
        return tuple(parsed), total

    async def get_family(
        self,
        publication: PatentNumber,
        family_type: FamilyType,
    ) -> PatentFamily:
        if family_type is not FamilyType.DOCDB_SIMPLE:
            raise ProviderResponseError(
                "Google Patents provider supports DOCDB simple-family fallback only."
            )

        url = f"{GOOGLE_PATENT_URL}/{publication.canonical}/en"
        async with httpx.AsyncClient(
            timeout=self.timeout_seconds,
            follow_redirects=True,
            headers={"User-Agent": self.user_agent},
        ) as client:
            response = await self._get(client, url, allow_not_found=True)
            if response is None:
                raise ProviderResponseError(
                    f"Google Patents did not find {publication.canonical}."
                )

        parser = _PatentPageParser()
        parser.feed(response.text)
        family = PatentFamily(
            family_type=FamilyType.DOCDB_SIMPLE,
            source="GOOGLE_PATENTS",
        )

        base_hit = _page_hit(parser, publication)
        family.add_member(
            PatentPublication(
                publication_number=base_hit.publication_number,
                jurisdiction=base_hit.jurisdiction,
                kind_code=base_hit.kind_code,
                application_number=_first(parser.values, "applicationNumber"),
                title=base_hit.title,
                filing_date=_parse_date(_first(parser.values, "filingDate")),
                publication_date=base_hit.publication_date,
                grant_date=_parse_date(_first(parser.values, "grantDate")),
                language="en",
                original_assignees=tuple(
                    dict.fromkeys(parser.values.get("assigneeOriginal", []))
                ),
                current_assignees=tuple(
                    dict.fromkeys(parser.values.get("assigneeCurrent", []))
                ),
            )
        )

        for number, publication_date in parser.family_members:
            jurisdiction, kind, canonical = _identity(number)
            family.add_member(
                PatentPublication(
                    publication_number=canonical,
                    jurisdiction=jurisdiction,
                    kind_code=kind,
                    publication_date=_parse_date(publication_date),
                    language="en",
                )
            )

        if not family.members:
            raise ProviderResponseError(
                "Google Patents page contained no simple-family members."
            )
        return family

    async def _get(
        self,
        client: httpx.AsyncClient,
        url: str,
        *,
        params: dict[str, str] | None = None,
        allow_not_found: bool = False,
    ) -> httpx.Response | None:
        if self.max_attempts < 1:
            raise ValueError("max_attempts must be >= 1")

        last_network_error: httpx.RequestError | None = None
        for attempt in range(1, self.max_attempts + 1):
            try:
                response = await client.get(url, params=params)
            except httpx.RequestError as exc:
                last_network_error = exc
                if attempt < self.max_attempts:
                    await asyncio.sleep(self.retry_delay_seconds * attempt)
                    continue
                raise ProviderUnavailableError(
                    f"Google Patents network error: {exc}"
                ) from exc

            if response.status_code == 404 and allow_not_found:
                return None

            throttled = response.status_code == 429 or (
                response.status_code == 503
                and "sorry" in response.text.casefold()
            )
            if throttled:
                if attempt < self.max_attempts:
                    await asyncio.sleep(self.retry_delay_seconds * attempt)
                    continue
                if response.status_code == 429:
                    raise ProviderRateLimitError(
                        "Google Patents rate limit reached (HTTP 429)."
                    )
                raise ProviderRateLimitError(
                    "Google Patents temporarily throttled automated requests (HTTP 503)."
                )

            if response.status_code >= 500:
                if attempt < self.max_attempts:
                    await asyncio.sleep(self.retry_delay_seconds * attempt)
                    continue
                raise ProviderUnavailableError(
                    f"Google Patents unavailable (HTTP {response.status_code})."
                )
            if response.status_code >= 400:
                raise ProviderResponseError(
                    f"Google Patents request failed (HTTP {response.status_code})."
                )
            return response

        if last_network_error is not None:
            raise ProviderUnavailableError(
                f"Google Patents network error: {last_network_error}"
            ) from last_network_error
        raise ProviderUnavailableError("Google Patents request failed after retries.")
