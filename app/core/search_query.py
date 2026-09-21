"""Compile provider-neutral search expressions to EPO OPS CQL."""

from __future__ import annotations

from app.domain.search import SearchExpression


def _cql_quote(value: str) -> str:
    clean = " ".join(value.strip().split())
    clean = clean.replace("\\", "\\\\").replace('"', '\\"')
    return f'"{clean}"'


def _or_group(clauses: list[str]) -> str:
    if not clauses:
        return ""
    if len(clauses) == 1:
        return clauses[0]
    return "(" + " or ".join(clauses) + ")"


def _classification_clause(code: str) -> str:
    clean = "".join(code.upper().split())
    return f'cl={_cql_quote(clean)}'


def _technology_clause(term: str) -> str:
    normalized = " ".join(term.split())
    if " " in normalized:
        return f"ta all {_cql_quote(normalized)}"
    return f"ta={_cql_quote(normalized)}"


def compile_epo_cql(expression: SearchExpression) -> str:
    """Compile a search expression using documented OPS CQL indexes.

    Applicant aliases are ORed. Distinct technology concept groups are ANDed,
    while synonyms inside each concept group are ORed.
    """
    groups: list[str] = []

    if expression.applicants:
        groups.append(
            _or_group([f"pa={_cql_quote(name)}" for name in expression.applicants])
        )

    if expression.text_terms:
        clauses = [_technology_clause(term) for term in expression.text_terms if term.strip()]
        if clauses:
            groups.append(_or_group(clauses))

    for text_group in expression.text_groups:
        clauses = [_technology_clause(term) for term in text_group if term.strip()]
        if clauses:
            groups.append(_or_group(clauses))

    for classification_group in expression.classification_groups:
        clauses = [_classification_clause(code) for code in classification_group if code.strip()]
        if clauses:
            groups.append(_or_group(clauses))

    portfolio_clauses = [
        *[_technology_clause(term) for term in expression.portfolio_terms if term.strip()],
        *[
            _classification_clause(code)
            for code in expression.portfolio_classifications
            if code.strip()
        ],
    ]
    if portfolio_clauses:
        groups.append(_or_group(portfolio_clauses))

    if expression.jurisdictions:
        groups.append(
            _or_group(
                [f"pn={jurisdiction.upper()}" for jurisdiction in expression.jurisdictions]
            )
        )

    if expression.published_from and expression.published_to:
        start = expression.published_from.strftime("%Y%m%d")
        end = expression.published_to.strftime("%Y%m%d")
        groups.append(f'pd within "{start} {end}"')
    elif expression.published_from:
        groups.append(f'pd>={expression.published_from.strftime("%Y%m%d")}')
    elif expression.published_to:
        groups.append(f'pd<={expression.published_to.strftime("%Y%m%d")}')

    if not groups:
        raise ValueError("Search expression is empty.")

    return " and ".join(groups)
