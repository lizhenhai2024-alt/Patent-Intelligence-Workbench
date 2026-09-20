"""EPO Open Patent Services adapter.

V1 P2 starts with INPADOC extended-family retrieval through the dedicated OPS
family service. DOCDB simple-family support will use the OPS Published Data
"equivalents" constituent in the next increment.
"""

from __future__ import annotations

import base64
import os
import xml.etree.ElementTree as ET
from dataclasses import dataclass
from datetime import date

import httpx

from app.core.patent_number import PatentNumber
from app.domain.family import FamilyType, PatentFamily, PatentPublication, PriorityClaim
from app.providers.base import (
    ProviderCapability,
    ProviderConfigurationError,
    ProviderInfo,
    ProviderResponseError,
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


def _publication_from_family_member(member: ET.Element) -> PatentPublication | None:
    publication_reference = next(
        (
            node
            for node in member
            if _local_name(node.tag) == "publication-reference"
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

    priorities: list[PriorityClaim] = []
    for node in member.iter():
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

    application_number: str | None = None
    for node in member:
        if _local_name(node.tag) != "application-reference":
            continue
        application_doc_id = _docdb_document_id(node)
        if application_doc_id is None:
            continue
        application_country = _first_child_text(application_doc_id, "country")
        application_doc_number = _first_child_text(application_doc_id, "doc-number")
        if application_country and application_doc_number:
            application_number = f"{application_country}{application_doc_number}"
            break

    return PatentPublication(
        publication_number=f"{country}{number}{kind or ''}",
        jurisdiction=country,
        kind_code=kind,
        application_number=application_number,
        publication_date=publication_date,
        priorities=tuple(priorities),
    )


def parse_extended_family_xml(xml_text: str) -> PatentFamily:
    """Parse an OPS family-service XML response into the internal domain model."""
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
        publication = _publication_from_family_member(member)
        if publication is not None:
            family.add_member(publication)

    if not family.members:
        raise ProviderResponseError("EPO OPS family response contained no usable family members.")
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
        response = await client.post(
            TOKEN_URL,
            headers={
                "Authorization": f"Basic {basic}",
                "Content-Type": "application/x-www-form-urlencoded",
            },
            content="grant_type=client_credentials",
        )
        response.raise_for_status()
        token = response.json().get("access_token")
        if not token:
            raise ProviderResponseError("EPO OPS token response did not include access_token.")
        return token

    async def get_family(
        self,
        publication: PatentNumber,
        family_type: FamilyType,
    ) -> PatentFamily:
        if family_type is not FamilyType.INPADOC_EXTENDED:
            raise NotImplementedError("DOCDB simple-family retrieval is scheduled for P2B.")

        async with httpx.AsyncClient(timeout=self.timeout_seconds) as client:
            token = await self._access_token(client)
            docdb = to_docdb_publication(publication)
            url = f"{OPS_BASE_URL}/family/publication/docdb/{docdb}"
            response = await client.get(
                url,
                headers={
                    "Authorization": f"Bearer {token}",
                    "Accept": "application/ops+xml",
                },
            )
            response.raise_for_status()
            return parse_extended_family_xml(response.text)
