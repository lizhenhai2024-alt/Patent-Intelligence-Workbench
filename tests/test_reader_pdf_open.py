from pathlib import Path
from types import SimpleNamespace

from app.desktop.app import PatentWorkbenchApp
from app.desktop.paths import AppPaths
from app.desktop.runtime import DesktopRuntime
from app.domain.search import SearchHit


def test_reader_pdf_prefers_existing_library_document(monkeypatch, tmp_path: Path):
    runtime = DesktopRuntime.create(paths=AppPaths.for_root(tmp_path / "appdata"))
    app = PatentWorkbenchApp(runtime)
    app.withdraw()
    pdf = tmp_path / "existing.pdf"
    pdf.write_bytes(b"%PDF-1.4\n")
    opened = []
    patent = SimpleNamespace(documents=(SimpleNamespace(path=pdf),))
    monkeypatch.setattr(runtime.library_store, "get_patent", lambda _number: patent)
    monkeypatch.setattr("app.desktop.app.open_local_path", lambda path: opened.append(Path(path)))
    app._reader_hit = SearchHit(publication_number="US20240003399A1", jurisdiction="US")

    app.open_reader_pdf()

    assert opened == [pdf]
    app.destroy()
    runtime.close()
