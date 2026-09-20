from datetime import UTC, datetime

from app.library.models import EvidenceRecord
from app.library.store import SQLitePatentLibrary


def test_evidence_roundtrip(tmp_path):
    store = SQLitePatentLibrary(tmp_path / "workbench.db")
    record = EvidenceRecord(
        evidence_id="ev-1",
        source="https://example.com/patent",
        source_type="WEB",
        title="Example",
        markdown="# Example",
        metadata_json='{"k":"v"}',
        captured_at=datetime.now(UTC),
        tags=("noise",),
    )
    store.add_evidence(record)
    rows = store.list_evidence(text="Example")
    assert len(rows) == 1
    assert rows[0].source == record.source
    assert rows[0].tags == ("noise",)
