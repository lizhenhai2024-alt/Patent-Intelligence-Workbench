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


def compile_epo_cql(expression: SearchExpression) -> str:
    """Compile a search expression using documented OPS CQL indexes.

    - applicant: pa
    - title or abstract: ta
    - publication number/country: pn
    - publication date: pd
    """
    groups: list[str] = []

    if expression.applicants:
        groups.append(
            _or_group([f"pa={_cql_quote(name)}" for name in expression.applicants])
        )

    if expression.text_terms:
        term_clauses = []
        for term in expression.text_terms:
            normalized = " ".join(term.split())
            if not normalized:
                continue
            if " " in normalized:
                term_clauses.append(f"ta all {_cql_quote(normalized)}")
            else:
                term_clauses.append(f"ta={_cql_quote(normalized)}")
        if term_clauses:
            groups.append(_or_group(term_clauses))

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
