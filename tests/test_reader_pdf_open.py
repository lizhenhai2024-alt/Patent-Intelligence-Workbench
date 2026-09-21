import asyncio
import os
from pathlib import Path
from types import SimpleNamespace

import pytest

from app.desktop.app import PatentWorkbenchApp
from app.desktop.paths import AppPaths
from app.desktop.runtime import DesktopRuntime
from app.domain.family import PatentPublication
from app.domain.search import SearchHit

pytestmark = pytest.mark.skipif(
    os.name != "nt" and not os.environ.get("DISPLAY"),
    reason="Tk UI tests require a display",
)


def _runtime(tmp_path: Path) -> DesktopRuntime:
    runtime = DesktopRuntime.create(paths=AppPaths.for_root(tmp_path / "appdata"))
    runtime.set_library_root(tmp_path / "PatentLibrary")
    return runtime


def test_reader_pdf_prefers_existing_library_document(monkeypatch, tmp_path: Path):
    runtime = _runtime(tmp_path)
    pdf = runtime.library_root / "Tenneco" / "US20240003399A1.pdf"
    pdf.parent.mkdir(parents=True, exist_ok=True)
    pdf.write_bytes(b"%PDF-1.4\n")
    runtime.library_store.upsert_publication(
        PatentPublication(
            publication_number="US20240003399A1",
            jurisdiction="US",
        ),
        source="TEST",
    )
    runtime.library_store.attach_pdf("US20240003399A1", pdf, provider="TEST")
    app = PatentWorkbenchApp(runtime)
    app.withdraw()
    opened = []
    monkeypatch.setattr(
        "app.desktop.app.open_local_path",
        lambda path: opened.append(Path(path)),
    )
    app._reader_hit = SearchHit(
        publication_number="US20240003399A1",
        jurisdiction="US",
    )

    async def should_not_download(*args, **kwargs):
        raise AssertionError("library hit must not download")

    monkeypatch.setattr(
        runtime.family_downloader.manager,
        "download",
        should_not_download,
    )
    app.open_reader_pdf()

    assert opened == [pdf]
    app.destroy()
    runtime.close()


def test_reader_pdf_downloads_into_library_and_registers(monkeypatch, tmp_path: Path):
    runtime = _runtime(tmp_path)
    app = PatentWorkbenchApp(runtime)
    app.withdraw()
    opened = []
    destinations = []
    hit = SearchHit(
        publication_number="US20240003399A1",
        jurisdiction="US",
        title="Pressure relief poppet valves for suspension dampers",
        applicants=("Driv Automotive Inc",),
    )
    app._reader_hit = hit
    monkeypatch.setattr(
        "app.desktop.app.open_local_path",
        lambda path: opened.append(Path(path)),
    )

    async def fake_download(publication, destination, *, overwrite=False):
        destination = Path(destination)
        destination.parent.mkdir(parents=True, exist_ok=True)
        destination.write_bytes(b"%PDF-1.4\n")
        destinations.append(destination)
        return SimpleNamespace(
            path=destination,
            provider="FAKE",
            source_url="https://example.com/patent.pdf",
        )

    def run_now(awaitable_factory, *, on_success, on_error, schedule_ui):
        try:
            result = asyncio.run(awaitable_factory())
        except Exception as exc:
            on_error(exc)
        else:
            on_success(result)
        return None

    monkeypatch.setattr(runtime.family_downloader.manager, "download", fake_download)
    monkeypatch.setattr("app.desktop.app.run_async_in_thread", run_now)

    app.open_reader_pdf()

    assert len(destinations) == 1
    destination = destinations[0]
    assert runtime.library_root in destination.parents
    assert "reader-cache" not in str(destination)
    stored = runtime.library_store.get_patent("US20240003399A1")
    assert stored is not None
    assert stored.documents
    assert stored.documents[0].path == destination
    assert opened == [destination]

    app.destroy()
    runtime.close()


def test_reader_pdf_finds_unindexed_file_in_library(monkeypatch, tmp_path: Path):
    runtime = _runtime(tmp_path)
    pdf = runtime.library_root / "待归类" / "US20240003399A1_local.pdf"
    pdf.parent.mkdir(parents=True, exist_ok=True)
    pdf.write_bytes(b"%PDF-1.4\n")
    app = PatentWorkbenchApp(runtime)
    app.withdraw()
    opened = []
    monkeypatch.setattr(
        "app.desktop.app.open_local_path",
        lambda path: opened.append(Path(path)),
    )
    app._reader_hit = SearchHit(
        publication_number="US20240003399A1",
        jurisdiction="US",
    )

    async def should_not_download(*args, **kwargs):
        raise AssertionError("existing library file must not download")

    monkeypatch.setattr(
        runtime.family_downloader.manager,
        "download",
        should_not_download,
    )
    app.open_reader_pdf()

    assert opened == [pdf]
    stored = runtime.library_store.get_patent("US20240003399A1")
    assert stored is not None
    assert stored.documents
    assert stored.documents[0].path == pdf
    app.destroy()
    runtime.close()
