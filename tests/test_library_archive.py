from datetime import date
from pathlib import Path

from app.library.archive import company_folder, patent_archive_path


def test_company_folder_sanitizes_display_separator(tmp_path: Path):
    folder = company_folder(tmp_path, "富奥东机工 / 一汽东机工")
    assert folder.parent == tmp_path
    assert folder.name == "富奥东机工 _ 一汽东机工"


def test_patent_archive_uses_knowledge_base_filename(tmp_path: Path):
    path = patent_archive_path(
        tmp_path,
        "富奥东机工",
        "CN120100850A",
        "一种浮动密封式电磁阀减振器",
        year=date(2025, 6, 6).year,
        assignee="一汽东机工减振器有限公司",
    )
    assert path.name == (
        "2025-CN120100850A-一种浮动密封式电磁阀减振器-"
        "一汽东机工减振器有限公司.pdf"
    )
