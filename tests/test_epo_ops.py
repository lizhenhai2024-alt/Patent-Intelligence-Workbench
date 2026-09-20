from datetime import date

from app.core.patent_number import normalize_patent_number
from app.domain.family import FamilyType
from app.providers.epo_ops import (
    parse_extended_family_xml,
    parse_simple_family_xml,
    to_docdb_publication,
)

EXTENDED_XML = """<?xml version="1.0" encoding="UTF-8"?>
<ops:world-patent-data
    xmlns:ops="http://ops.epo.org"
    xmlns:exchange="http://www.epo.org/exchange">
  <ops:patent-family family-id="F-123">
    <ops:family-member>
      <exchange:publication-reference>
        <exchange:document-id document-id-type="docdb">
          <exchange:country>JP</exchange:country>
          <exchange:doc-number>2024000123</exchange:doc-number>
          <exchange:kind>A</exchange:kind>
          <exchange:date>20240115</exchange:date>
        </exchange:document-id>
      </exchange:publication-reference>
      <exchange:application-reference>
        <exchange:document-id document-id-type="docdb">
          <exchange:country>JP</exchange:country>
          <exchange:doc-number>2023000123</exchange:doc-number>
        </exchange:document-id>
      </exchange:application-reference>
      <exchange:priority-claim kind="national">
        <exchange:document-id document-id-type="docdb">
          <exchange:country>JP</exchange:country>
          <exchange:doc-number>2022000456</exchange:doc-number>
          <exchange:date>20220304</exchange:date>
        </exchange:document-id>
      </exchange:priority-claim>
    </ops:family-member>
    <ops:family-member>
      <exchange:publication-reference>
        <exchange:document-id document-id-type="docdb">
          <exchange:country>WO</exchange:country>
          <exchange:doc-number>2024123456</exchange:doc-number>
          <exchange:kind>A1</exchange:kind>
          <exchange:date>20240620</exchange:date>
        </exchange:document-id>
      </exchange:publication-reference>
      <exchange:priority-claim kind="national">
        <exchange:document-id document-id-type="docdb">
          <exchange:country>JP</exchange:country>
          <exchange:doc-number>2022000456</exchange:doc-number>
          <exchange:date>20220304</exchange:date>
        </exchange:document-id>
      </exchange:priority-claim>
    </ops:family-member>
  </ops:patent-family>
</ops:world-patent-data>
"""

SIMPLE_XML = """<?xml version="1.0" encoding="UTF-8"?>
<ops:world-patent-data
    xmlns:ops="http://ops.epo.org"
    xmlns="http://www.epo.org/exchange">
  <ops:equivalents-inquiry>
    <ops:inquiry-result>
      <exchange-documents>
        <exchange-document family-id="19768124" country="JP"
                           doc-number="2024000123" kind="A">
          <bibliographic-data>
            <publication-reference>
              <document-id document-id-type="docdb">
                <country>JP</country>
                <doc-number>2024000123</doc-number>
                <kind>A</kind>
                <date>20240115</date>
              </document-id>
            </publication-reference>
            <application-reference>
              <document-id document-id-type="docdb">
                <country>JP</country>
                <doc-number>2023000123</doc-number>
              </document-id>
            </application-reference>
            <priority-claims>
              <priority-claim kind="national">
                <document-id document-id-type="docdb">
                  <country>JP</country>
                  <doc-number>2022000456</doc-number>
                  <date>20220304</date>
                </document-id>
              </priority-claim>
            </priority-claims>
          </bibliographic-data>
        </exchange-document>
      </exchange-documents>
    </ops:inquiry-result>
    <ops:inquiry-result>
      <exchange-documents>
        <exchange-document family-id="19768124" country="WO"
                           doc-number="2024123456" kind="A1">
          <bibliographic-data>
            <publication-reference>
              <document-id document-id-type="docdb">
                <country>WO</country>
                <doc-number>2024123456</doc-number>
                <kind>A1</kind>
                <date>20240620</date>
              </document-id>
            </publication-reference>
            <priority-claims>
              <priority-claim kind="national">
                <document-id document-id-type="docdb">
                  <country>JP</country>
                  <doc-number>2022000456</doc-number>
                  <date>20220304</date>
                </document-id>
              </priority-claim>
            </priority-claims>
          </bibliographic-data>
        </exchange-document>
      </exchange-documents>
    </ops:inquiry-result>
  </ops:equivalents-inquiry>
</ops:world-patent-data>
"""


def test_parse_extended_family_xml():
    family = parse_extended_family_xml(EXTENDED_XML)
    assert family.family_type is FamilyType.INPADOC_EXTENDED
    assert family.source == "EPO_OPS"
    assert family.source_family_id == "F-123"
    assert family.member_numbers() == ("JP2024000123A", "WO2024123456A1")
    assert family.earliest_priority is not None
    assert family.earliest_priority.priority_date == date(2022, 3, 4)


def test_parse_simple_family_xml():
    family = parse_simple_family_xml(SIMPLE_XML)
    assert family.family_type is FamilyType.DOCDB_SIMPLE
    assert family.source_family_id == "19768124"
    assert family.member_numbers() == ("JP2024000123A", "WO2024123456A1")
    assert family.earliest_priority is not None
    assert family.earliest_priority.number == "JP2022000456"


def test_to_docdb_publication():
    publication = normalize_patent_number("EP 1000000 A1")
    assert to_docdb_publication(publication) == "EP.1000000.A1"
