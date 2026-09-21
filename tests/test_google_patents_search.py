import asyncio

import httpx
import pytest

from app.core.patent_number import normalize_patent_number
from app.domain.search import SearchExpression
from app.providers.base import ProviderRateLimitError
from app.providers.google_patents_search import (
    GooglePatentsSearchProvider,
    _expression_text,
    _page_hit,
    _PatentPageParser,
    _search_hit_from_json,
)


def test_structured_json_hit_is_cleaned_and_normalized():
    hit = _search_hit_from_json(
        {
            "publication_number": "US10962081B2",
            "title": " <b>Damper</b> with dual springs ",
            "assignee": "<b>Tenneco</b> Automotive Operating Company Inc.",
            "publication_date": "2021-03-30",
        }
    )

    assert hit is not None
    assert hit.publication_number == "US10962081B2"
    assert hit.title == "Damper with dual springs"
    assert hit.applicants == ("Tenneco Automotive Operating Company Inc.",)
    assert hit.source == "GOOGLE_PATENTS"


def test_patent_page_parser_reads_bibliography_and_docdb_family():
    html = """
    <article>
      <span itemprop="title">Controlled damper</span>
      <dd itemprop="publicationNumber">EP1000000A1</dd>
      <dd itemprop="assigneeCurrent">Example GmbH</dd>
      <time itemprop="publicationDate" datetime="2000-05-17"></time>
      <tr itemprop="docdbFamily" itemscope>
        <span itemprop="publicationNumber">US6093011A</span>
        <td itemprop="publicationDate">2000-07-25</td>
      </tr>
    </article>
    """
    parser = _PatentPageParser()
    parser.feed(html)
    hit = _page_hit(parser, normalize_patent_number("EP1000000A1"))

    assert hit.title == "Controlled damper"
    assert hit.applicants == ("Example GmbH",)
    assert hit.publication_date.isoformat() == "2000-05-17"
    assert parser.family_members == [("US6093011A", "2000-07-25")]


class FakeClient:
    def __init__(self, response):
        self.response = response

    async def get(self, url, params=None):
        return self.response


def test_google_sorry_503_is_classified_as_rate_limit():
    response = httpx.Response(
        503,
        text="<html><title>Sorry...</title></html>",
        request=httpx.Request("GET", "https://patents.google.com/"),
    )
    provider = GooglePatentsSearchProvider(max_attempts=1)

    with pytest.raises(ProviderRateLimitError):
        asyncio.run(
            provider._get(
                FakeClient(response),
                "https://patents.google.com/",
            )
        )


class SequenceClient:
    def __init__(self, responses):
        self.responses = list(responses)
        self.calls = 0

    async def get(self, url, params=None):
        response = self.responses[self.calls]
        self.calls += 1
        return response


def test_google_throttle_retries_then_succeeds():
    request = httpx.Request("GET", "https://patents.google.com/")
    throttled = httpx.Response(
        503,
        text="<html><title>Sorry...</title></html>",
        request=request,
    )
    success = httpx.Response(200, text="ok", request=request)
    client = SequenceClient((throttled, success))
    provider = GooglePatentsSearchProvider(
        max_attempts=2,
        retry_delay_seconds=0,
    )

    response = asyncio.run(
        provider._get(client, "https://patents.google.com/")
    )

    assert response is success
    assert client.calls == 2


def test_google_expression_includes_portfolio_terms():
    expression = SearchExpression(
        applicants=("Bose Corporation",),
        portfolio_terms=(
            "vehicle suspension",
            "shock absorber",
            "active suspension",
        ),
    )

    text = _expression_text(expression)

    assert '"vehicle suspension"' in text
    assert '"shock absorber"' in text
    assert '"active suspension"' in text
    assert " OR " in text
