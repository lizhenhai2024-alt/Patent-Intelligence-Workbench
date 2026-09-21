from pathlib import Path

from app.library.local_patent_index import import_patent_folder
from app.library.store import SQLitePatentLibrary


def _write_astemo_index(folder: Path, relative_path: str) -> None:
    (folder / "ASTEMO_Patent_Index.csv").write_text(
        '"Year","Publication","Country","Category","Tag","Filename","Path"\n'
        '"2024","US20240003399A1","US",'
        '"01_电控减振器_CDC_电磁阀","先导阀背压腔",'
        '"2024-US20240003399A1-demo.pdf",'
        f'"{relative_path}"\n',
        encoding="utf-8-sig",
    )


def test_astemo_index_maps_category_and_nested_pdf(tmp_path: Path):
    folder = tmp_path / "ASTEMO"
    pdf = folder / "01_电控减振器_CDC_电磁阀" / "A" / "demo_US20240003399A1.pdf"
    pdf.parent.mkdir(parents=True)
    pdf.write_bytes(b"%PDF-1.4")
    _write_astemo_index(
        folder,
        r"01_电控减振器_CDC_电磁阀\A\demo_US20240003399A1.pdf",
    )
    store = SQLitePatentLibrary(tmp_path / "library.db")
    summary = import_patent_folder(store, folder, company_group="astemo")

    assert summary.imported == 1
    assert summary.attached_pdfs == 1
    assert summary.classified == 1
    patent = store.get_patent("US20240003399A1")
    assert patent is not None
    assert patent.title is None
    assert "astemo" in patent.company_groups
    assert "Semi-active" in patent.technology_topics
    assert "CDC / CVSA" in patent.technology_topics
    assert "Pilot Valve" in patent.technology_topics
    assert "Back-pressure Control" in patent.technology_topics
    assert "先导阀背压腔" in patent.tags
    assert patent.documents[0].path == pdf
    store.close()


def test_import_dry_run_does_not_mutate_store(tmp_path: Path):
    folder = tmp_path / "ASTEMO"
    pdf = folder / "01_电控减振器_CDC_电磁阀" / "US20240003399A1.pdf"
    pdf.parent.mkdir(parents=True)
    pdf.write_bytes(b"%PDF-1.4")
    _write_astemo_index(
        folder,
        r"01_电控减振器_CDC_电磁阀\US20240003399A1.pdf",
    )
    store = SQLitePatentLibrary(tmp_path / "library.db")
    summary = import_patent_folder(
        store,
        folder,
        company_group="astemo",
        dry_run=True,
    )

    assert summary.imported == 1
    assert summary.attached_pdfs == 1
    assert summary.classified == 1
    assert store.get_patent("US20240003399A1") is None
    store.close()



def test_legacy_filename_recovers_title_without_assignee_guess(tmp_path: Path):
    folder = tmp_path / "FTL"
    folder.mkdir()
    pdf = folder / "CN120100850A_一种浮动密封式电磁阀减振器.pdf"
    pdf.write_bytes(b"%PDF-1.4")

    store = SQLitePatentLibrary(tmp_path / "library.db")
    summary = import_patent_folder(store, folder, company_group="ftl")
    patent = store.get_patent("CN120100850A")

    assert summary.imported == 1
    assert patent is not None
    assert patent.title == "一种浮动密封式电磁阀减振器"
    assert patent.original_assignees == ()
    store.close()



def test_canonical_filename_does_not_guess_title_or_assignee(tmp_path: Path):
    folder = tmp_path / "ASTEMO"
    folder.mkdir()
    pdf = folder / "2025-US20250001234A1-Damper valve-Hitachi Astemo.pdf"
    pdf.write_bytes(b"%PDF-1.4")

    store = SQLitePatentLibrary(tmp_path / "library.db")
    summary = import_patent_folder(store, folder, company_group="astemo")
    patent = store.get_patent("US20250001234A1")

    assert summary.imported == 1
    assert patent is not None
    assert patent.title is None
    assert patent.original_assignees == ()
    store.close()
