from app.core.patent_number import normalize_patent_number
from app.providers.epo_publication_server import EpoPublicationServerProvider
from app.providers.google_patents import parse_citation_pdf_url


def test_epo_publication_server_supports_ep_and_builds_official_pdf_url():
    provider = EpoPublicationServerProvider()
    publication = normalize_patent_number("EP1502502A1")

    assert provider.supports(publication)
    assert (
        provider.pdf_url(publication)
        == "https://data.epo.org/publication-server/pdf-document"
        "?cc=EP&pn=1502502&ki=A1"
    )


def test_epo_publication_server_rejects_non_ep():
    provider = EpoPublicationServerProvider()
    publication = normalize_patent_number("JP2024000123A")

    assert not provider.supports(publication)


def test_google_patents_parser_extracts_citation_pdf_url():
    html = """
    <html><head>
      <meta name="citation_title" content="Example">
      <meta name="citation_pdf_url"
            content="https://patentimages.storage.googleapis.com/example.pdf">
    </head></html>
    """

    assert (
        parse_citation_pdf_url(html)
        == "https://patentimages.storage.googleapis.com/example.pdf"
    )
