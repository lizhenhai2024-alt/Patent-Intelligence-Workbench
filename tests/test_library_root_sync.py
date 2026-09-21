from pathlib import Path

from app.library.root_sync import sync_library_root
from app.library.store import SQLitePatentLibrary


def test_sync_library_root_imports_company_folders(tmp_path: Path):
    root = tmp_path / "PatentLibrary"
    known = root / "一汽东机工"
    known.mkdir(parents=True)
    (known / "CN120100850A_一种电磁阀减振器.pdf").write_bytes(b"pdf")

    unknown = root / "UnknownCo"
    unknown.mkdir()
    (unknown / "US20240000001A1_Test damper.pdf").write_bytes(b"pdf")

    store = SQLitePatentLibrary(tmp_path / "library.db")
    summary = sync_library_root(store, root)

    assert summary.folders == 2
    assert summary.imported == 2
    assert summary.attached_pdfs == 2
    assert summary.unknown_folders == ("UnknownCo",)

    known_patent = store.get_patent("CN120100850A")
    unknown_patent = store.get_patent("US20240000001A1")
    assert known_patent is not None
    assert "ftl" in known_patent.company_groups
    assert known_patent.original_assignees == ()
    assert unknown_patent is not None
    assert unknown_patent.company_groups == ()
    store.close()
