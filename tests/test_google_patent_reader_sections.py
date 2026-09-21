from app.providers.google_patents_search import _PatentPageParser


def test_patent_page_parser_extracts_claims_and_description():
    html = """
    <html><body>
      <section itemprop="description">
        <div><p>A damper includes a piston rod.</p></div>
        <p>The valve controls flow.</p>
      </section>
      <section itemprop="claims">
        <div><p>1. A suspension damper comprising a pilot valve.</p></div>
        <div><p>2. The damper of claim 1 comprising a floating piston.</p></div>
      </section>
      <section>
        <h2>Images</h2>
        <ul>
          <li itemprop="images">
            <img itemprop="thumbnail" src="https://example.com/thumb.png">
            <meta itemprop="full" content="https://example.com/full.png">
          </li>
        </ul>
      </section>
    </body></html>
    """
    parser = _PatentPageParser()
    parser.feed(html)

    assert parser.sections["description"] == [
        "A damper includes a piston rod.",
        "The valve controls flow.",
    ]
    assert parser.sections["claims"] == [
        "1. A suspension damper comprising a pilot valve.",
        "2. The damper of claim 1 comprising a floating piston.",
    ]
    assert parser.figures[0].thumbnail_url == "https://example.com/thumb.png"
    assert parser.figures[0].full_url == "https://example.com/full.png"
