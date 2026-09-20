from datetime import date

from app.domain.family import FamilyType, PatentFamily, PatentPublication, PriorityClaim


def test_family_returns_earliest_priority():
    family = PatentFamily(
        family_type=FamilyType.INPADOC_EXTENDED,
        source="TEST",
        members=[
            PatentPublication(
                publication_number="JP2024000001A",
                jurisdiction="JP",
                priorities=(
                    PriorityClaim("JP2023000001", "JP", date(2023, 2, 2)),
                ),
            ),
            PatentPublication(
                publication_number="WO2024123456A1",
                jurisdiction="WO",
                priorities=(
                    PriorityClaim("JP2022000001", "JP", date(2022, 3, 1)),
                ),
            ),
        ],
    )
    assert family.earliest_priority is not None
    assert family.earliest_priority.number == "JP2022000001"


def test_family_deduplicates_publication_number():
    family = PatentFamily(FamilyType.DOCDB_SIMPLE, source="TEST")
    publication = PatentPublication("EP1234567A1", "EP")
    family.add_member(publication)
    family.add_member(publication)
    assert family.member_numbers() == ("EP1234567A1",)
