from datetime import date

from app.providers.epo_ops import (
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


def test_parse_biblio_search_extracts_abstract_and_classification():
    xml = SEARCH_XML.replace(
        '<invention-title lang="en">Active suspension damper</invention-title>',
        '<invention-title lang="en">Active suspension damper</invention-title>'
        '<classifications-ipcr><classification-ipcr><text>B60G11/16</text>'
        '</classification-ipcr></classifications-ipcr>'
        '<abstract lang="en"><p>Upper spring seat for a vehicle suspension.</p></abstract>',
    )
    hit = parse_biblio_search_xml(xml).hits[0]
    assert hit.abstract == "Upper spring seat for a vehicle suspension."
    assert hit.classifications == ("B60G11/16",)
