import json
from tkinter import font as tkfont
from tkinter import ttk

import pytest

from app.desktop.app import PatentWorkbenchApp
from app.desktop.paths import AppPaths
from app.desktop.reader_appearance import (
    MAX_SIZE,
    MAX_SPACING,
    MIN_SIZE,
    MIN_SPACING,
    ReaderAppearance,
)
from app.desktop.runtime import DesktopRuntime
from app.desktop.tk_runtime import can_run_tk_tests
from app.domain.reader import PatentReaderDocument

pytestmark = pytest.mark.skipif(
    not can_run_tk_tests(), reason="Tk UI tests require a usable Tcl/Tk runtime",
)


@pytest.fixture(scope="module")
def reader_app(tmp_path_factory):
    runtime = DesktopRuntime.create(AppPaths.for_root(tmp_path_factory.mktemp("reader-style")))
    instance = PatentWorkbenchApp(runtime)
    instance.withdraw()
    yield instance
    instance._on_close()


@pytest.fixture
def app(reader_app):
    reader_app.reader_appearance.reset()
    return reader_app


def text_size(app, widget):
    return tkfont.Font(root=app, font=widget.cget("font")).actual("size")


def test_controls_change_both_panes_without_changing_content(app):
    appearance = app.reader_appearance
    app.reader_source_text.insert("1.0", "Original patent text")
    app._set_reader_translation("专利译文")
    app.reader_source_text.tag_add("sel", "1.0", "1.8")
    appearance.larger.invoke()
    appearance.looser.invoke()
    for widget in (app.reader_source_text, app.reader_translation_text):
        assert text_size(app, widget) == 12
        assert int(widget.cget("spacing2")) == 2
    assert app.reader_source_text.get("1.0", "end-1c").startswith("Original patent text")
    assert app.reader_source_text.get("sel.first", "sel.last") == "Original"
    assert app.reader_translation_text.get("1.0", "end-1c") == "专利译文"
    assert str(app.reader_translation_text.cget("state")) == "disabled"
    assert app._reader_figure_zoom_level == 0
    appearance.smaller.invoke()
    appearance.tighter.invoke()
    assert text_size(app, app.reader_source_text) == 11
    assert int(app.reader_translation_text.cget("spacing2")) == 1


def test_font_selection_and_style_survive_section_changes_and_reload(app):
    appearance = app.reader_appearance
    selected = tkfont.nametofont("TkDefaultFont", root=app).actual("family")
    appearance.family.set(selected)
    appearance.font_box.event_generate("<<ComboboxSelected>>")
    appearance.larger.invoke()
    appearance.looser.invoke()
    app._reader_document = PatentReaderDocument(
        publication_number="US20240003399A1", abstract="Abstract", claims="1. A valve.",
    )
    app.reader_section_var.set("权利要求")
    app._render_reader_section()
    app._set_reader_translation("1. 一种阀。")
    saved = json.loads(appearance.path.read_text(encoding="utf-8"))
    assert saved == {"family": selected, "size": 12, "spacing": 2}
    # Reconstruct from disk, just as the Reader does on application startup.
    host = ttk.Frame(app)
    try:
        restored = ReaderAppearance(host, appearance.path, app._set_status)
        restored.attach(app.reader_source_text, app.reader_translation_text)
        for widget in (app.reader_source_text, app.reader_translation_text):
            font = tkfont.Font(root=app, font=widget.cget("font"))
            assert font.actual("family") == selected
            assert font.actual("size") == 12
            assert int(widget.cget("spacing2")) == 2
        assert app.reader_source_text.get("1.0", "end-1c") == "1. A valve."
    finally:
        host.destroy()


def test_limits_reset_and_save_failure(app):
    appearance = app.reader_appearance
    appearance.change_size(100)
    appearance.change_spacing(100)
    assert appearance.size == MAX_SIZE
    assert appearance.spacing == MAX_SPACING
    assert appearance.larger.instate(["disabled"])
    assert appearance.looser.instate(["disabled"])
    appearance.change_size(-100)
    appearance.change_spacing(-100)
    assert appearance.size == MIN_SIZE
    assert appearance.spacing == MIN_SPACING
    assert appearance.smaller.instate(["disabled"])
    assert appearance.tighter.instate(["disabled"])
    appearance.reset_button.invoke()
    assert (appearance.size, appearance.spacing) == (11, 1)
    original_path = appearance.path
    try:
        appearance.path = original_path / "missing-directory" / "settings.json"
        appearance.larger.invoke()
        assert text_size(app, app.reader_translation_text) == 12
        assert "保存失败" in app.status_var.get()
    finally:
        appearance.path = original_path


@pytest.mark.parametrize("payload", ["invalid json", "[]", '{"size": true,"spacing":"bad"}',
                                     '{"family":[],"size":999,"spacing":-10}'])
def test_invalid_settings_do_not_break_reader(app, tmp_path, payload):
    path = tmp_path / "reader-appearance.json"
    path.write_text(payload, encoding="utf-8")
    host = ttk.Frame(app)
    try:
        restored = ReaderAppearance(host, path, app._set_status)
        restored.attach(app.reader_source_text, app.reader_translation_text)
        assert MIN_SIZE <= text_size(app, app.reader_source_text) <= MAX_SIZE
        assert MIN_SPACING <= restored.spacing <= MAX_SPACING
    finally:
        host.destroy()
