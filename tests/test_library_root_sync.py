from pathlib import Path

from app.library.root_sync import sync_library_root
from app.library.store import SQLitePatentLibrary


def test_sync_library_root_imports_company_folders(tmp_path: Path):
    root = tmp_path / "PatentLibrary"
    patents_root = root / "10_Patents"
    known = patents_root / "一汽东机工"
    known.mkdir(parents=True)
    nested = known / "01_电控减振器_CDC_电磁阀"
    nested.mkdir()
    (nested / "CN120100850A_一种电磁阀减振器.pdf").write_bytes(b"pdf")

    unknown = patents_root / "UnknownCo"
    unknown.mkdir()
    (unknown / "US20240000001A1_Test damper.pdf").write_bytes(b"pdf")

    store = SQLitePatentLibrary(tmp_path / "library.db")
    summary = sync_library_root(store, root)

    assert summary.folders == 2
    assert summary.imported == 2
    assert summary.attached_pdfs == 2
    assert summary.unknown_folders == ("UnknownCo",)
    assert summary.classified >= 1

    known_patent = store.get_patent("CN120100850A")
    unknown_patent = store.get_patent("US20240000001A1")
    assert known_patent is not None
    assert "ftl" in known_patent.company_groups
    assert "Semi-active" in known_patent.technology_topics
    assert known_patent.original_assignees == ()
    assert unknown_patent is not None
    assert unknown_patent.company_groups == ()

    second = sync_library_root(store, root)
    assert second.imported == 2
    assert len(store.query()) == 2
    assert len(store.get_patent("CN120100850A").documents) == 1
    store.close()


def test_sync_library_root_dry_run_is_read_only(tmp_path: Path):
    root = tmp_path / "PatentLibrary" / "10_Patents" / "ASTEMO"
    root.mkdir(parents=True)
    (root / "US20240003399A1.pdf").write_bytes(b"pdf")

    store = SQLitePatentLibrary(tmp_path / "library.db")
    summary = sync_library_root(store, tmp_path / "PatentLibrary", dry_run=True)

    assert summary.dry_run is True
    assert summary.imported == 1
    assert store.get_patent("US20240003399A1") is None
    store.close()
