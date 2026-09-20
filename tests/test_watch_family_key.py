from datetime import date

from app.domain.family import FamilyType, PatentFamily, PatentPublication, PriorityClaim
from app.watch.family_key import derive_family_key


def test_family_key_prefers_provider_family_id():
    family = PatentFamily(
        family_type=FamilyType.DOCDB_SIMPLE,
        source="EPO_OPS",
        source_family_id="12345",
    )

    assert derive_family_key(family) == "DOCDB_SIMPLE:EPO_OPS:12345"


def test_family_key_falls_back_to_earliest_priority():
    priority = PriorityClaim("JP2023000001", "JP", date(2023, 1, 2))
    family = PatentFamily(
        family_type=FamilyType.DOCDB_SIMPLE,
        source="TEST",
        members=[
            PatentPublication(
                publication_number="JP2024000001A",
                jurisdiction="JP",
                priorities=(priority,),
            )
        ],
    )

    assert derive_family_key(family) == "DOCDB_SIMPLE:PRIORITY:JP2023000001:2023-01-02"
