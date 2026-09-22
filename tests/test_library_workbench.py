from datetime import date

from app.domain.family import (
    Classification,
    FamilyType,
    PatentFamily,
    PatentPublication,
    PriorityClaim,
)
from app.library.store import SQLitePatentLibrary
from app.library.workbench import (
    library_metadata_summary,
    library_patent_to_search_hit,
    library_patents_to_family,
    preferred_library_folder,
    preferred_library_pdf,
)


def _library_patent(tmp_path):
    library = SQLitePatentLibrary(tmp_path / "library.db")
    priority = PriorityClaim(
        number="DE102022000001",
        country="DE",
        priority_date=date(2022, 3, 4),
    )
    family = PatentFamily(
        family_type=FamilyType.DOCDB_SIMPLE,
        source="EPO_OPS",
        source_family_id="F-READER",
        members=[
            PatentPublication(
                publication_number="EP4317739A1",
                jurisdiction="EP",
                kind_code="A1",
                title="Pressure relief valve for suspension damper",
                publication_date=date(2024, 2, 7),
                current_assignees=("Tenneco Automotive Operating Company Inc.",),
                priorities=(priority,),
                classifications=(
                    Classification("CPC", "F16F9/46", True),
                    Classification("CPC", "B60G17/08"),
                ),
            ),
            PatentPublication(
                publication_number="US20240003399A1",
                jurisdiction="US",
                kind_code="A1",
                title="Pressure relief valve for suspension damper",
                publication_date=date(2024, 1, 4),
                current_assignees=("Tenneco Automotive Operating Company Inc.",),
                priorities=(priority,),
            ),
        ],
    )
    library.upsert_family(family)
    pdf = tmp_path / "PatentLibrary" / "10_Patents" / "Tenneco" / "EP4317739A1.pdf"
    pdf.parent.mkdir(parents=True)
    pdf.write_bytes(b"%PDF-test")
    library.attach_pdf(
        "EP4317739A1",
        pdf,
        provider="EPO_OPS",
        source_url="https://example.test/EP4317739A1.pdf",
    )
    library.add_provenance("EP4317739A1", "SEARCH", "EPO_OPS")
    patent = library.get_patent("EP4317739A1")
    assert patent is not None
    return library, patent, pdf


def test_library_patent_adapts_to_reader_search_hit(tmp_path):
    library, patent, _ = _library_patent(tmp_path)
    try:
        hit = library_patent_to_search_hit(patent)
        assert hit.publication_number == "EP4317739A1"
        assert hit.title == "Pressure relief valve for suspension damper"
        assert hit.applicants == ("Tenneco Automotive Operating Company Inc.",)
        assert hit.classifications == ("F16F9/46", "B60G17/08")
        assert hit.source == "EPO_OPS"
    finally:
        library.close()


def test_library_workbench_prefers_existing_pdf_and_patent_folder(tmp_path):
    library, patent, pdf = _library_patent(tmp_path)
    try:
        assert preferred_library_pdf(patent) == pdf
        assert preferred_library_folder(
            patent,
            library_root=tmp_path / "PatentLibrary",
        ) == pdf.parent
    finally:
        library.close()


def test_library_metadata_summary_exposes_engineering_context(tmp_path):
    library, patent, _ = _library_patent(tmp_path)
    try:
        summary = library_metadata_summary(patent)
        assert "Tenneco Automotive Operating Company Inc." in summary
        assert "2024-02-07" in summary
        assert "2022-03-04" in summary
        assert "F-READER" in summary
        assert "F16F9/46" in summary
        assert "B60G17/08" in summary
        assert "SEARCH" in summary
    finally:
        library.close()


def test_local_family_can_be_reconstructed_without_network(tmp_path):
    library, patent, _ = _library_patent(tmp_path)
    try:
        assert patent.family_key is not None
        members = library.get_family_members(patent.family_key)
        family = library_patents_to_family(members)
        assert family is not None
        assert family.family_type is FamilyType.DOCDB_SIMPLE
        assert family.source_family_id == "F-READER"
        assert family.member_numbers() == (
            "US20240003399A1",
            "EP4317739A1",
        )
    finally:
        library.close()
