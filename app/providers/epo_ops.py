"""EPO Open Patent Services adapter.

Supports:
- bibliographic search using documented OPS CQL indexes,
- direct publication lookup,
- INPADOC extended-family retrieval,
- DOCDB simple-family retrieval through Published Data equivalents.
"""

from __future__ import annotations

import base64
import os
import xml.etree.ElementTree as ET
from dataclasses import dataclass
from datetime import date

import httpx

from app.core.patent_number import PatentNumber
from app.core.search_query import compile_epo_cql
from app.domain.family import FamilyType, PatentFamily, PatentPublication, PriorityClaim
from app.domain.search import SearchExpression, SearchHit, SearchPage
from app.providers.base import (
    ProviderAuthenticationError,
    ProviderCapability,
    ProviderConfigurationError,
    ProviderInfo,
    ProviderRateLimitError,
    ProviderResponseError,
    ProviderUnavailableError,
)

TOKEN_URL = "https://ops.epo.org/3.2/auth/accesstoken"
OPS_BASE_URL = "https://ops.epo.org/3.2/rest-services"


def _local_name(tag: str) -> str:
    return tag.rsplit("}", 1)[-1]


def _first_child_text(element: ET.Element, local_name: str) -> str | None:
    for child in element.iter():
        if _local_name(child.tag) == local_name and child.text:
            return child.text.strip()
    return None


def _parse_yyyymmdd(value: str | None) -> date | None:
    if not value or len(value) != 8 or not value.isdigit():
        return None
    return date(int(value[:4]), int(value[4:6]), int(value[6:8]))


def _docdb_document_id(container: ET.Element) -> ET.Element | None:
    for element in container.iter():
        if _local_name(element.tag) != "document-id":
            continue
        if element.attrib.get("document-id-type", "").lower() == "docdb":
            return element
    return None


def _priority_claims(container: ET.Element) -> tuple[PriorityClaim, ...]:
    priorities: list[PriorityClaim] = []
    for node in container.iter():
        if _local_name(node.tag) != "priority-claim":
            continue
        priority_doc_id = _docdb_document_id(node)
        if priority_doc_id is None:
            continue
        priority_country = _first_child_text(priority_doc_id, "country")
        priority_number = _first_child_text(priority_doc_id, "doc-number")
        if not priority_country or not priority_number:
            continue
        priorities.append(
            PriorityClaim(
                number=f"{priority_country}{priority_number}",
                country=priority_country,
                priority_date=_parse_yyyymmdd(_first_child_text(priority_doc_id, "date")),
                priority_type=node.attrib.get("kind"),
            )
        )
    return tuple(priorities)


def _application_number(container: ET.Element) -> str | None:
    for node in container.iter():
        if _local_name(node.tag) != "application-reference":
            continue
        application_doc_id = _docdb_document_id(node)
        if application_doc_id is None:
            continue
        country = _first_child_text(application_doc_id, "country")
        number = _first_child_text(application_doc_id, "doc-number")
        if country and number:
            return f"{country}{number}"
    return None


def _publication_from_docdb_container(container: ET.Element) -> PatentPublication | None:
    publication_reference = next(
        (
            node
            for node in container.iter()
            if _local_name(node.tag) == "publication-reference"
            and _docdb_document_id(node) is not None
        ),
        None,
    )
    if publication_reference is None:
        return None

    doc_id = _docdb_document_id(publication_reference)
    if doc_id is None:
        return None

    country = _first_child_text(doc_id, "country")
    number = _first_child_text(doc_id, "doc-number")
    kind = _first_child_text(doc_id, "kind")
    publication_date = _parse_yyyymmdd(_first_child_text(doc_id, "date"))
    if not country or not number:
        return None

    return PatentPublication(
        publication_number=f"{country}{number}{kind or ''}",
        jurisdiction=country,
        kind_code=kind,
        application_number=_application_number(container),
        title=_extract_title(container),
        publication_date=publication_date,
        original_assignees=_extract_applicants(container),
        priorities=_priority_claims(container),
    )


def _extract_title(container: ET.Element) -> str | None:
    english: str | None = None
    fallback: str | None = None
    for node in container.iter():
        if _local_name(node.tag) != "invention-title" or not node.text:
            continue
        value = " ".join(node.text.split())
        if not value:
            continue
        language = (
            node.attrib.get("lang")
            or node.attrib.get("{http://www.w3.org/XML/1998/namespace}lang")
            or ""
        ).lower()
        if language == "en":
            english = value
            break
        if fallback is None:
            fallback = value
    return english or fallback


def _extract_applicants(container: ET.Element) -> tuple[str, ...]:
    names: list[str] = []
    for applicant in container.iter():
        if _local_name(applicant.tag) != "applicant":
            continue
        name = _first_child_text(applicant, "name")
        if name and name not in names:
            names.append(name)
    return tuple(names)


def _extract_abstract(container: ET.Element) -> str | None:
    paragraphs: list[str] = []
    for node in container.iter():
        if _local_name(node.tag) != "abstract":
            continue
        for child in node.iter():
            if _local_name(child.tag) != "p" or not child.text:
                continue
            value = " ".join(child.text.split())
            if value:
                paragraphs.append(value)
        if paragraphs:
            break
    return " ".join(paragraphs) or None


def _extract_classifications(container: ET.Element) -> tuple[str, ...]:
    values: list[str] = []
    for node in container.iter():
        local = _local_name(node.tag)
        if local not in {"classification-ipcr", "classification-cpc"}:
            continue
        value = _first_child_text(node, "text") or " ".join(node.itertext()).strip()
        value = "".join(value.split()).upper()
        if value and value not in values:
            values.append(value)
    return tuple(values)


def _search_hit_from_exchange_document(container: ET.Element) -> SearchHit | None:
    publication = _publication_from_docdb_container(container)
    if publication is None:
        return None
    return SearchHit(
        publication_number=publication.publication_number,
        jurisdiction=publication.jurisdiction,
        kind_code=publication.kind_code,
        title=_extract_title(container),
        abstract=_extract_abstract(container),
        applicants=_extract_applicants(container),
        classifications=_extract_classifications(container),
        publication_date=publication.publication_date,
        source="EPO_OPS",
    )


def parse_biblio_search_xml(xml_text: str) -> SearchPage:
    """Parse OPS Published Data bibliographic-search XML."""
    try:
        root = ET.fromstring(xml_text)
    except ET.ParseError as exc:
        raise ProviderResponseError("Invalid XML from EPO OPS search service.") from exc

    search = next(
        (node for node in root.iter() if _local_name(node.tag) == "biblio-search"),
        None,
    )
    if search is None:
        raise ProviderResponseError("EPO OPS response did not contain biblio-search.")

    total_text = search.attrib.get("total-result-count")
    total = int(total_text) if total_text and total_text.isdigit() else None

    range_element = next(
        (node for node in search.iter() if _local_name(node.tag) == "range"),
        None,
    )
    range_begin = None
    range_end = None
    if range_element is not None:
        begin = range_element.attrib.get("begin")
        end = range_element.attrib.get("end")
        range_begin = int(begin) if begin and begin.isdigit() else None
        range_end = int(end) if end and end.isdigit() else None

    hits: list[SearchHit] = []
    seen: set[str] = set()
    for node in search.iter():
        if _local_name(node.tag) != "exchange-document":
            continue
        hit = _search_hit_from_exchange_document(node)
        if hit is None or hit.publication_number in seen:
            continue
        seen.add(hit.publication_number)
        hits.append(hit)

    return SearchPage(
        hits=tuple(hits),
        total_result_count=total,
        range_begin=range_begin,
        range_end=range_end,
    )


def parse_publication_biblio_xml(xml_text: str) -> SearchPage:
    """Parse direct publication bibliographic retrieval XML."""
    try:
        root = ET.fromstring(xml_text)
    except ET.ParseError as exc:
        raise ProviderResponseError("Invalid XML from EPO OPS biblio service.") from exc

    hits: list[SearchHit] = []
    seen: set[str] = set()
    for node in root.iter():
        if _local_name(node.tag) != "exchange-document":
            continue
        hit = _search_hit_from_exchange_document(node)
        if hit is None or hit.publication_number in seen:
            continue
        seen.add(hit.publication_number)
        hits.append(hit)

    if not hits:
        raise ProviderResponseError("EPO OPS biblio response contained no usable publication.")

    return SearchPage(
        hits=tuple(hits),
        total_result_count=len(hits),
        range_begin=1,
        range_end=len(hits),
    )


def parse_extended_family_xml(xml_text: str) -> PatentFamily:
    """Parse an OPS family-service XML response into an INPADOC family."""
    try:
        root = ET.fromstring(xml_text)
    except ET.ParseError as exc:
        raise ProviderResponseError("Invalid XML from EPO OPS family service.") from exc

    patent_family = next(
        (node for node in root.iter() if _local_name(node.tag) == "patent-family"),
        None,
    )
    if patent_family is None:
        raise ProviderResponseError("EPO OPS response did not contain a patent-family element.")

    family = PatentFamily(
        family_type=FamilyType.INPADOC_EXTENDED,
        source="EPO_OPS",
        source_family_id=patent_family.attrib.get("family-id"),
    )

    for member in patent_family:
        if _local_name(member.tag) != "family-member":
            continue
        publication = _publication_from_docdb_container(member)
        if publication is not None:
            family.add_member(publication)

    if not family.members:
        raise ProviderResponseError("EPO OPS family response contained no usable family members.")
    return family


def parse_simple_family_xml(xml_text: str) -> PatentFamily:
    """Parse Published Data equivalents/biblio XML into a DOCDB simple family."""
    try:
        root = ET.fromstring(xml_text)
    except ET.ParseError as exc:
        raise ProviderResponseError("Invalid XML from EPO OPS equivalents service.") from exc

    equivalents = next(
        (node for node in root.iter() if _local_name(node.tag) == "equivalents-inquiry"),
        None,
    )
    if equivalents is None:
        raise ProviderResponseError(
            "EPO OPS response did not contain an equivalents-inquiry element."
        )

    family = PatentFamily(
        family_type=FamilyType.DOCDB_SIMPLE,
        source="EPO_OPS",
    )

    family_ids: list[str] = []
    for exchange_document in equivalents.iter():
        if _local_name(exchange_document.tag) != "exchange-document":
            continue
        family_id = exchange_document.attrib.get("family-id")
        if family_id:
            family_ids.append(family_id)
        publication = _publication_from_docdb_container(exchange_document)
        if publication is not None:
            family.add_member(publication)

    if family_ids:
        family.source_family_id = family_ids[0]

    if not family.members:
        raise ProviderResponseError(
            "EPO OPS equivalents response contained no usable simple-family members."
        )
    return family


def to_docdb_publication(publication: PatentNumber) -> str:
    """Convert the internal canonical publication token to OPS DOCDB notation."""
    body = publication.number_without_kind[2:]
    suffix = f".{publication.kind_code}" if publication.kind_code else ""
    return f"{publication.jurisdiction}.{body}{suffix}"


@dataclass(slots=True)
class EpoOpsProvider:
    consumer_key: str | None = None
    consumer_secret: str | None = None
    timeout_seconds: float = 30.0

    info = ProviderInfo(
        name="EPO_OPS",
        capabilities=frozenset(
            {
                ProviderCapability.SEARCH,
                ProviderCapability.PUBLICATION_LOOKUP,
                ProviderCapability.FAMILY_SIMPLE,
                ProviderCapability.FAMILY_EXTENDED,
                ProviderCapability.BIBLIOGRAPHY,
                ProviderCapability.LEGAL_STATUS,
            }
        ),
    )

    def __post_init__(self) -> None:
        self.consumer_key = self.consumer_key or os.getenv("EPO_OPS_KEY")
        self.consumer_secret = self.consumer_secret or os.getenv("EPO_OPS_SECRET")

    def _require_credentials(self) -> tuple[str, str]:
        if not self.consumer_key or not self.consumer_secret:
            raise ProviderConfigurationError(
                "EPO OPS credentials are required. Set EPO_OPS_KEY and EPO_OPS_SECRET."
            )
        return self.consumer_key, self.consumer_secret

    async def _access_token(self, client: httpx.AsyncClient) -> str:
        key, secret = self._require_credentials()
        basic = base64.b64encode(f"{key}:{secret}".encode()).decode()
        try:
            response = await client.post(
                TOKEN_URL,
                headers={
                    "Authorization": f"Basic {basic}",
                    "Content-Type": "application/x-www-form-urlencoded",
                },
                content="grant_type=client_credentials",
            )
        except httpx.RequestError as exc:
            raise ProviderUnavailableError(
                f"EPO OPS OAuth network error: {exc}"
            ) from exc

        if response.status_code in {401, 403}:
            raise ProviderAuthenticationError(
                "EPO OPS rejected the configured credentials."
            )
        if response.status_code == 429:
            raise ProviderRateLimitError("EPO OPS rate limit reached (HTTP 429).")
        if response.status_code >= 500:
            raise ProviderUnavailableError(
                f"EPO OPS OAuth service unavailable (HTTP {response.status_code})."
            )
        if response.status_code >= 400:
            raise ProviderResponseError(
                f"EPO OPS OAuth request failed (HTTP {response.status_code})."
            )

        token = response.json().get("access_token")
        if not token:
            raise ProviderResponseError("EPO OPS token response did not include access_token.")
        return token

    async def _authorized_get(
        self,
        client: httpx.AsyncClient,
        url: str,
        *,
        token: str,
        params: dict[str, str] | None = None,
        headers: dict[str, str] | None = None,
    ) -> httpx.Response:
        request_headers = {
            "Authorization": f"Bearer {token}",
            "Accept": "application/ops+xml",
        }
        if headers:
            request_headers.update(headers)
        try:
            response = await client.get(
                url,
                headers=request_headers,
                params=params,
            )
        except httpx.RequestError as exc:
            raise ProviderUnavailableError(
                f"EPO OPS network error for {url}: {exc}"
            ) from exc

        if response.status_code in {401, 403}:
            raise ProviderAuthenticationError(
                f"EPO OPS rejected authentication for {url}."
            )
        if response.status_code == 429:
            raise ProviderRateLimitError(
                f"EPO OPS rate limit reached for {url} (HTTP 429)."
            )
        if response.status_code >= 500:
            raise ProviderUnavailableError(
                f"EPO OPS unavailable for {url} (HTTP {response.status_code})."
            )
        if response.status_code >= 400:
            raise ProviderResponseError(
                f"EPO OPS request failed for {url} (HTTP {response.status_code})."
            )
        return response

    async def lookup_publication(self, publication: PatentNumber) -> SearchPage:
        async with httpx.AsyncClient(timeout=self.timeout_seconds) as client:
            token = await self._access_token(client)
            docdb = to_docdb_publication(publication)
            url = (
                f"{OPS_BASE_URL}/published-data/publication/docdb/"
                f"{docdb}/biblio"
            )
            response = await self._authorized_get(client, url, token=token)
            return parse_publication_biblio_xml(response.text)

    async def search_publications(
        self,
        expression: SearchExpression,
        *,
        page_size: int = 25,
        page_start: int = 1,
    ) -> SearchPage:
        if page_size < 1 or page_size > 100:
            raise ValueError("EPO OPS page_size must be between 1 and 100.")
        if page_start < 1:
            raise ValueError("page_start must be >= 1.")

        cql = compile_epo_cql(expression)
        page_end = page_start + page_size - 1

        async with httpx.AsyncClient(timeout=self.timeout_seconds) as client:
            token = await self._access_token(client)
            url = f"{OPS_BASE_URL}/published-data/search/biblio"
            response = await self._authorized_get(
                client,
                url,
                token=token,
                params={"q": cql},
                headers={"X-OPS-Range": f"{page_start}-{page_end}"},
            )
            return parse_biblio_search_xml(response.text)

    async def get_family(
        self,
        publication: PatentNumber,
        family_type: FamilyType,
    ) -> PatentFamily:
        async with httpx.AsyncClient(timeout=self.timeout_seconds) as client:
            token = await self._access_token(client)
            docdb = to_docdb_publication(publication)

            if family_type is FamilyType.INPADOC_EXTENDED:
                url = f"{OPS_BASE_URL}/family/publication/docdb/{docdb}"
                parser = parse_extended_family_xml
            elif family_type is FamilyType.DOCDB_SIMPLE:
                url = (
                    f"{OPS_BASE_URL}/published-data/publication/docdb/"
                    f"{docdb}/equivalents/biblio"
                )
                parser = parse_simple_family_xml
            else:
                raise ValueError(f"Unsupported family type: {family_type}")

            response = await self._authorized_get(client, url, token=token)
            return parser(response.text)
