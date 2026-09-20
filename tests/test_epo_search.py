import asyncio
from datetime import date

import httpx

from app.domain.search import SearchExpression
from app.providers.epo_ops import (
    OPS_BASE_URL,
    EpoOpsProvider,
    parse_biblio_search_xml,
    parse_publication_biblio_xml,
)

SEARCH_XML = """<?xml version="1.0" encoding="UTF-8"?>
<ops:world-patent-data
    xmlns:ops="http://ops.epo.org"
    xmlns="http://www.epo.org/exchange">
  <ops:biblio-search total-result-count="42">
    <ops:query syntax="CQL">pa="TEST"</ops:query>
    <ops:range begin="1" end="2"/>
    <ops:search-result>
      <exchange-documents>
        <exchange-document country="JP" doc-number="2024000123" kind="A">
          <bibliographic-data>
            <publication-reference>
              <document-id document-id-type="docdb">
                <country>JP</country>
                <doc-number>2024000123</doc-number>
                <kind>A</kind>
                <date>20240115</date>
              </document-id>
            </publication-reference>
            <parties>
              <applicants>
                <applicant>
                  <applicant-name><name>TEST JAPAN LTD</name></applicant-name>
                </applicant>
              </applicants>
            </parties>
            <invention-title lang="en">Active suspension damper</invention-title>
          </bibliographic-data>
        </exchange-document>
        <exchange-document country="US" doc-number="20240123456" kind="A1">
          <bibliographic-data>
            <publication-reference>
              <document-id document-id-type="docdb">
                <country>US</country>
                <doc-number>20240123456</doc-number>
                <kind>A1</kind>
                <date>20240502</date>
              </document-id>
            </publication-reference>
            <invention-title lang="en">Pilot valve assembly</invention-title>
          </bibliographic-data>
        </exchange-document>
      </exchange-documents>
    </ops:search-result>
  </ops:biblio-search>
</ops:world-patent-data>
"""

BIBLIO_XML = """<?xml version="1.0" encoding="UTF-8"?>
<ops:world-patent-data
    xmlns:ops="http://ops.epo.org"
    xmlns="http://www.epo.org/exchange">
  <ops:exchange-documents>
    <exchange-document country="EP" doc-number="1000000" kind="A1">
      <bibliographic-data>
        <publication-reference>
          <document-id document-id-type="docdb">
            <country>EP</country>
            <doc-number>1000000</doc-number>
            <kind>A1</kind>
            <date>20000517</date>
          </document-id>
        </publication-reference>
        <invention-title lang="en">Example patent</invention-title>
      </bibliographic-data>
    </exchange-document>
  </ops:exchange-documents>
</ops:world-patent-data>
"""


def test_parse_biblio_search_xml():
    page = parse_biblio_search_xml(SEARCH_XML)

    assert page.total_result_count == 42
    assert page.range_begin == 1
    assert page.range_end == 2
    assert len(page.hits) == 2
    assert page.hits[0].publication_number == "JP2024000123A"
    assert page.hits[0].title == "Active suspension damper"
    assert page.hits[0].applicants == ("TEST JAPAN LTD",)
    assert page.hits[0].publication_date == date(2024, 1, 15)


def test_parse_direct_publication_biblio_xml():
    page = parse_publication_biblio_xml(BIBLIO_XML)

    assert page.total_result_count == 1
    assert page.hits[0].publication_number == "EP1000000A1"
    assert page.hits[0].title == "Example patent"


def test_epo_search_404_no_results_is_empty_page(monkeypatch):
    captured = {}

    async def fake_token(self, client):
        return "token"

    async def fake_get(
        self,
        client,
        url,
        *,
        token,
        params=None,
        headers=None,
        allow_not_found=False,
    ):
        captured["url"] = url
        captured["allow_not_found"] = allow_not_found
        request = httpx.Request("GET", url)
        return httpx.Response(
            404,
            text=(
                '<?xml version="1.0" encoding="UTF-8"?>'
                '<fault xmlns="http://ops.epo.org">'
                '<code>SERVER.EntityNotFound</code>'
                '<message>No results found</message>'
                '</fault>'
            ),
            request=request,
        )

    monkeypatch.setattr(EpoOpsProvider, "_access_token", fake_token)
    monkeypatch.setattr(EpoOpsProvider, "_authorized_get", fake_get)

    provider = EpoOpsProvider("key", "secret")
    page = asyncio.run(
        provider.search_publications(
            SearchExpression(applicants=("BWI",), text_terms=("damper",)),
            page_size=10,
        )
    )

    assert page.hits == ()
    assert page.total_result_count == 0
    assert captured["url"] == f"{OPS_BASE_URL}/published-data/search"
    assert captured["allow_not_found"] is True
