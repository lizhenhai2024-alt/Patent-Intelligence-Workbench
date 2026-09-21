from app.providers.epo_ops import (
    parse_fulltext_section_xml,
    parse_image_layout_xml,
)

CLAIMS_XML = """<?xml version="1.0" encoding="UTF-8"?>
<ops:world-patent-data
    xmlns:ops="http://ops.epo.org"
    xmlns:ftxt="http://www.epo.org/fulltext">
  <ftxt:fulltext-documents>
    <ftxt:fulltext-document>
      <claims lang="EN">
        <claim>
          <claim-text>1. A damper comprising a pressure tube.</claim-text>
          <claim-text>a piston disposed in the pressure tube.</claim-text>
        </claim>
        <claim>
          <claim-text>2. The damper of claim 1 comprising a relief valve.</claim-text>
        </claim>
      </claims>
    </ftxt:fulltext-document>
  </ftxt:fulltext-documents>
</ops:world-patent-data>
"""


DESCRIPTION_XML = """<?xml version="1.0" encoding="UTF-8"?>
<ops:world-patent-data
    xmlns:ops="http://ops.epo.org"
    xmlns:ftxt="http://www.epo.org/fulltext">
  <ftxt:fulltext-documents>
    <ftxt:fulltext-document>
      <description lang="EN">
        <p>FIELD</p>
        <p>[0001] The disclosure relates to suspension dampers.</p>
      </description>
    </ftxt:fulltext-document>
  </ftxt:fulltext-documents>
</ops:world-patent-data>
"""


IMAGES_XML = """<?xml version="1.0" encoding="UTF-8"?>
<ops:world-patent-data xmlns:ops="http://ops.epo.org">
  <ops:document-inquiry>
    <ops:inquiry-result>
      <ops:document-instance
          system="ops.epo.org"
          number-of-pages="26"
          desc="FullDocument"
          link="published-data/images/CN/117329258/A/fullimage">
        <ops:document-section name="BIBLIOGRAPHY" start-page="1"/>
        <ops:document-section name="CLAIMS" start-page="2"/>
        <ops:document-section name="DESCRIPTION" start-page="4"/>
        <ops:document-section name="DRAWINGS" start-page="16"/>
      </ops:document-instance>
    </ops:inquiry-result>
  </ops:document-inquiry>
</ops:world-patent-data>
"""


def test_parse_epo_claims_preserves_claim_boundaries():
    text = parse_fulltext_section_xml(CLAIMS_XML, "claims")

    assert text.startswith("1. A damper comprising a pressure tube.")
    assert "2. The damper of claim 1" in text
    assert "\n\n2." in text


def test_parse_epo_description_preserves_paragraphs():
    text = parse_fulltext_section_xml(DESCRIPTION_XML, "description")

    assert text == "FIELD\n\n[0001] The disclosure relates to suspension dampers."


def test_parse_epo_image_layout_resolves_section_ranges():
    layout = parse_image_layout_xml(IMAGES_XML)

    assert layout is not None
    assert layout.total_pages == 26
    assert layout.start_page("CLAIMS") == 2
    assert layout.end_page("CLAIMS") == 3
    assert layout.start_page("DESCRIPTION") == 4
    assert layout.end_page("DESCRIPTION") == 15
    assert layout.start_page("DRAWINGS") == 16
    assert layout.end_page("DRAWINGS") == 26
