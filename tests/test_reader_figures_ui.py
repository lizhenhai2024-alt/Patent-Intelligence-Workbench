
import pytest

from app.desktop.app import PatentWorkbenchApp
from app.desktop.runtime import DesktopRuntime
from app.desktop.tk_runtime import can_run_tk_tests
from app.domain.reader import PatentFigure, PatentReaderDocument

pytestmark = pytest.mark.skipif(
    not can_run_tk_tests(),
    reason="Tk UI tests require a usable Tcl/Tk runtime",
)


def test_reader_figure_navigation(monkeypatch):
    runtime = DesktopRuntime.create()
    app = PatentWorkbenchApp(runtime)
    app.withdraw()
    app._reader_document = PatentReaderDocument(
        publication_number="US20240003399A1",
        figures=(
            PatentFigure("https://example.com/t1.png", "https://example.com/f1.png"),
            PatentFigure("https://example.com/t2.png", "https://example.com/f2.png"),
        ),
    )
    loaded = []
    monkeypatch.setattr(app, "_load_reader_figure_image", lambda url: loaded.append(url))
    app.reader_section_var.set("附图")
    app._render_reader_section()
    assert "附图 1/2" in app.reader_figure_info_var.get()
    assert loaded[-1] == "https://example.com/f1.png"
    app.reader_next_figure()
    assert "附图 2/2" in app.reader_figure_info_var.get()
    assert loaded[-1] == "https://example.com/f2.png"
    app.reader_next_figure()
    assert "附图 1/2" in app.reader_figure_info_var.get()
    opened = []
    monkeypatch.setattr("app.desktop.app.webbrowser.open", lambda url: opened.append(url))
    app.open_reader_figure()
    assert opened == ["https://example.com/f1.png"]
    app.destroy()
    runtime.close()
