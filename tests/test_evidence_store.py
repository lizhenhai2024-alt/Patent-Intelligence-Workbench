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


def test_evidence_filters(tmp_path):
    store = SQLitePatentLibrary(tmp_path / "workbench.db")
    store.add_evidence(
        EvidenceRecord(
            evidence_id="ev-filter",
            source="https://example.com/filter",
            source_type="WEB",
            title="Valve evidence",
            markdown="# Valve",
            metadata_json="{}",
            captured_at=datetime.now(UTC),
            company_group="ASTEMO",
            technology_topic="CDC",
        )
    )

    assert len(store.list_evidence(source_type="WEB")) == 1
    assert len(store.list_evidence(company_group="ASTEMO")) == 1
    assert len(store.list_evidence(technology_topic="CDC")) == 1
    assert store.list_evidence(source_type="FILE") == ()
