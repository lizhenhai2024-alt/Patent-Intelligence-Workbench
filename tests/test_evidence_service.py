from datetime import UTC, datetime

from app.library.service import PatentLibraryService
from app.library.store import SQLitePatentLibrary


def test_save_acquisition_evidence_can_link_patent(tmp_path):
    store = SQLitePatentLibrary(tmp_path / "workbench.db")
    service = PatentLibraryService(store)
    record = service.save_acquisition_evidence(
        source="https://example.com",
        source_type="web",
        markdown="content",
        publication_number="US20240003399A1",
        metadata={"source": "test"},
        captured_at=datetime.now(UTC),
    )
    assert record.publication_number == "US20240003399A1"
    patent = store.get_patent("US20240003399A1")
    assert patent is not None
    evidence = store.list_evidence(publication_number="US20240003399A1")
    assert len(evidence) == 1
