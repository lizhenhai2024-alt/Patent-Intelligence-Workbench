from pathlib import Path

from app.core.company_registry import CompanyRegistry
from app.library.local_patent_index import import_patent_folder
from app.library.store import SQLitePatentLibrary


def test_ftl_aliases_resolve_exactly():
    registry = CompanyRegistry.default()
    assert registry.get("一汽东机工").group_id == "ftl"
    assert registry.get("富奥东机工").group_id == "ftl"
    assert registry.get("一汽东机工减振器有限公司").group_id == "ftl"


def test_company_registry_no_longer_uses_substring_matching():
    registry = CompanyRegistry.default()
    try:
        registry.get("一汽")
    except KeyError:
        pass
    else:
        raise AssertionError("generic parent-company substring must not resolve")


def test_local_patent_folder_imports_csv_and_pdf(tmp_path: Path):
    folder = tmp_path / "ftl"
    folder.mkdir()
    (folder / "patent_list_complete.csv").write_text(
        "公开号,申请号,专利名称,申请日,公开日,专利类型,申请人,来源\n"
        "CN120100850A,,一种浮动密封式电磁阀减振器,2025-05-12,2025-06-06,发明专利,,本地\n",
        encoding="utf-8-sig",
    )
    (folder / "CN120100850A_一种浮动密封式电磁阀减振器.pdf").write_bytes(b"pdf")
    store = SQLitePatentLibrary(tmp_path / "library.db")
    summary = import_patent_folder(
        store,
        folder,
        company_group="ftl",
        default_assignee="一汽东机工减振器有限公司",
    )
    patent = store.get_patent("CN120100850A")
    assert summary.imported == 1
    assert summary.attached_pdfs == 1
    assert patent is not None
    assert patent.title == "一种浮动密封式电磁阀减振器"
    assert patent.original_assignees == ("一汽东机工减振器有限公司",)
    assert patent.company_groups == ("ftl",)
    assert len(patent.documents) == 1
    store.close()
