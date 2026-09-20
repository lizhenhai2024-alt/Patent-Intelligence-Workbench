import pytest

from app.core.patent_number import PatentNumberError, normalize_patent_number


@pytest.mark.parametrize(
    ("raw", "canonical", "jurisdiction", "kind_code"),
    [
        ("CN 115123456 A", "CN115123456A", "CN", "A"),
        ("CN115123456A", "CN115123456A", "CN", "A"),
        ("JP 2024-123456 A", "JP2024123456A", "JP", "A"),
        ("EP 4 123 456 A1", "EP4123456A1", "EP", "A1"),
        ("US 2024/0123456 A1", "US20240123456A1", "US", "A1"),
        ("US 11,234,567 B2", "US11234567B2", "US", "B2"),
        ("WO 2024/123456 A1", "WO2024123456A1", "WO", "A1"),
        ("KR 10-2024-0012345 A", "KR1020240012345A", "KR", "A"),
    ],
)
def test_normalize_patent_number(raw, canonical, jurisdiction, kind_code):
    result = normalize_patent_number(raw)
    assert result.canonical == canonical
    assert result.jurisdiction == jurisdiction
    assert result.kind_code == kind_code


def test_same_publication_with_different_format_normalizes_identically():
    a = normalize_patent_number("WO 2024/123456 A1")
    b = normalize_patent_number("WO2024123456A1")
    assert a.canonical == b.canonical


@pytest.mark.parametrize(
    "raw",
    ["", "123456", "XX123456A1", "CN---", "JPABC"],
)
def test_invalid_numbers_raise(raw):
    with pytest.raises(PatentNumberError):
        normalize_patent_number(raw)
