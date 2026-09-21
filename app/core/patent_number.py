"""Patent number normalization for V1 jurisdictions.

The normalizer intentionally separates formatting cleanup from legal-number
semantics. Provider adapters may later enrich the normalized result with
application/publication/grant relationships.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

SUPPORTED_JURISDICTIONS = frozenset({"CN", "DE", "JP", "EP", "US", "WO", "KR"})
_KIND_CODE_RE = re.compile(r"([A-Z]{1,2}\d{0,2})$")
_SEPARATORS_RE = re.compile(r"[\s\-_/.,:;()\[\]{}]+")


class PatentNumberError(ValueError):
    """Raised when a patent number cannot be normalized safely."""


@dataclass(frozen=True, slots=True)
class PatentNumber:
    raw: str
    jurisdiction: str
    canonical: str
    number_without_kind: str
    kind_code: str | None


def normalize_patent_number(raw: str) -> PatentNumber:
    """Normalize a publication-style patent number into a canonical token.

    Examples:
        CN 115123456 A      -> CN115123456A
        JP 2024-123456 A    -> JP2024123456A
        US 2024/0123456 A1  -> US20240123456A1
        WO 2024/123456 A1   -> WO2024123456A1

    The function does not infer a missing jurisdiction and does not convert an
    application number into a publication number. That distinction belongs to
    provider-specific enrichment.
    """
    if not isinstance(raw, str) or not raw.strip():
        raise PatentNumberError("Patent number must be a non-empty string.")

    text = raw.strip().upper()
    text = text.replace("–", "-").replace("—", "-").replace("−", "-")
    compact = _SEPARATORS_RE.sub("", text)

    if len(compact) < 4:
        raise PatentNumberError(f"Patent number is too short: {raw!r}")

    jurisdiction = compact[:2]
    if jurisdiction not in SUPPORTED_JURISDICTIONS:
        raise PatentNumberError(
            f"Unsupported or missing jurisdiction in {raw!r}; "
            f"expected one of {sorted(SUPPORTED_JURISDICTIONS)}."
        )

    body = compact[2:]
    if not body or not re.fullmatch(r"[A-Z0-9]+", body):
        raise PatentNumberError(f"Invalid characters in patent number: {raw!r}")

    kind_code: str | None = None
    number_body = body
    match = _KIND_CODE_RE.search(body)
    if match:
        candidate = match.group(1)
        prefix = body[: -len(candidate)]
        # Require a numeric publication/application body before treating the
        # suffix as a kind code. This avoids consuming all-letter identifiers.
        if prefix and any(ch.isdigit() for ch in prefix):
            kind_code = candidate
            number_body = prefix

    if not any(ch.isdigit() for ch in number_body):
        raise PatentNumberError(f"Patent number has no numeric body: {raw!r}")

    number_without_kind = f"{jurisdiction}{number_body}"
    canonical = f"{number_without_kind}{kind_code or ''}"

    return PatentNumber(
        raw=raw,
        jurisdiction=jurisdiction,
        canonical=canonical,
        number_without_kind=number_without_kind,
        kind_code=kind_code,
    )
