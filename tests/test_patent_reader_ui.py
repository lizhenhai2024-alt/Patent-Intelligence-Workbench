from app.desktop.app import PatentWorkbenchApp
from app.desktop.runtime import DesktopRuntime
from app.domain.search import SearchHit


def test_reader_opens_selected_search_hit():
    runtime = DesktopRuntime.create()
    app = PatentWorkbenchApp(runtime)
    app.withdraw()
    hit = SearchHit(
        publication_number="US20240003399A1",
        jurisdiction="US",
        title="Pilot controlled damper",
        abstract="A pilot valve controls a floating piston.",
        classifications=("F16F9/46",),
    )
    app._search_hits_by_number[hit.publication_number] = hit
    app.search_tree.insert(
        "",
        "end",
        iid=hit.publication_number,
        values=(hit.publication_number, "US", hit.title, "", "", ""),
    )
    app.search_tree.selection_set(hit.publication_number)
    app._open_selected_in_reader()

    assert app.reader_number_var.get() == hit.publication_number
    assert "Pilot controlled damper" in app.reader_source_text.get("1.0", "end")
    assert "F16F9/46" in app.reader_classification_var.get()
    assert app._pages["reader"].winfo_manager() == "pack"

    app.translate_reader_abstract()
    assert "翻译服务尚未配置" in app.reader_translation_text.get("1.0", "end")
    app.destroy()
    runtime.close()
