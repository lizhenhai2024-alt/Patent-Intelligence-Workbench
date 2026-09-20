from datetime import date

from app.core.search_query import compile_epo_cql
from app.domain.search import SearchExpression


def test_company_technology_query_compiles_to_boolean_cql():
    expression = SearchExpression(
        applicants=(
            "Tenneco Automotive Operating Company Inc.",
            "Monroe Auto Equipment Company",
        ),
        text_terms=("pilot valve", "damper"),
        jurisdictions=("JP", "US"),
    )

    cql = compile_epo_cql(expression)

    assert 'pa="Tenneco Automotive Operating Company Inc."' in cql
    assert 'pa="Monroe Auto Equipment Company"' in cql
    assert 'ta all "pilot valve"' in cql
    assert 'ta="damper"' in cql
    assert "(pn=JP or pn=US)" in cql


def test_distinct_technology_concepts_are_anded_and_synonyms_are_ored():
    expression = SearchExpression(
        text_groups=(
            ("pilot valve", "solenoid valve"),
            ("back pressure", "back pressure chamber"),
        ),
    )

    cql = compile_epo_cql(expression)

    pilot_group = '(ta all "pilot valve" or ta all "solenoid valve")'
    pressure_group = '(ta all "back pressure" or ta all "back pressure chamber")'
    assert f"{pilot_group} and {pressure_group}" == cql


def test_publication_date_range_uses_ops_within_syntax():
    expression = SearchExpression(
        text_terms=("active suspension",),
        published_from=date(2025, 1, 1),
        published_to=date(2026, 9, 20),
    )

    cql = compile_epo_cql(expression)

    assert 'pd within "20250101 20260920"' in cql
