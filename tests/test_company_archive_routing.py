import os
from pathlib import Path

import pytest

from app.desktop.app import PatentWorkbenchApp
from app.desktop.paths import AppPaths
from app.desktop.runtime import DesktopRuntime
from app.domain.family import FamilyType, PatentFamily, PatentPublication

pytestmark = pytest.mark.skipif(
    os.name != "nt" and not os.environ.get("DISPLAY"),
    reason="Tk UI tests require a display",
)


def test_known_company_download_root_uses_company_folder(tmp_path: Path):
    runtime = DesktopRuntime.create(paths=AppPaths.for_root(tmp_path / "appdata"))
    runtime.set_library_root(tmp_path / "PatentLibrary")
    app = PatentWorkbenchApp(runtime)
    app.withdraw()
    family = PatentFamily(
        family_type=FamilyType.DOCDB_SIMPLE,
        source="TEST",
        members=[
            PatentPublication(
                publication_number="CN120100850A",
                jurisdiction="CN",
                original_assignees=("一汽东机工减振器有限公司",),
            )
        ],
    )
    assert app._family_company_folder_name(family) == "富奥东机工"
    app.destroy()
    runtime.close()


def test_unknown_company_falls_back_to_pending_classification(tmp_path: Path):
    runtime = DesktopRuntime.create(paths=AppPaths.for_root(tmp_path / "appdata"))
    app = PatentWorkbenchApp(runtime)
    app.withdraw()
    family = PatentFamily(
        family_type=FamilyType.DOCDB_SIMPLE,
        source="TEST",
        members=[
            PatentPublication(
                publication_number="US20240000001A1",
                jurisdiction="US",
            )
        ],
    )
    assert app._family_company_folder_name(family) == "待归类"
    app.destroy()
    runtime.close()
