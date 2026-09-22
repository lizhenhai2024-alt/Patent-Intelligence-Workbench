import time

import pytest

from app.desktop.app import PatentWorkbenchApp
from app.desktop.intelligence_tab import copy_ai_prompt, run_task, send_to_search
from app.desktop.paths import AppPaths
from app.desktop.runtime import DesktopRuntime
from app.desktop.tk_runtime import can_run_tk_tests
from app.domain.family import PatentPublication
from app.intelligence.analysis import AnalysisScope, AnalysisService

pytestmark = pytest.mark.skipif(
    not can_run_tk_tests(), reason="Tk UI tests require a usable Tcl/Tk runtime"
)


def test_intelligence_tab_previews_editable_engineering_search(tmp_path, monkeypatch):
    runtime = DesktopRuntime.create(paths=AppPaths.for_root(tmp_path / "appdata"))
    app = PatentWorkbenchApp(runtime)
    app.withdraw()
    try:
        assert "intelligence" in app._pages
        app._show_page("intelligence")
        app.intelligence_workflow_var.set("工程问题检索")
        assert "把工程问题转换" in app.intelligence_task_context_var.get()
        assert not app._intelligence_field_frames["companies"].winfo_ismapped()
        app.intelligence_topic_var.set("CDC 减振器低温响应变慢")
        run_task(app)
        assert app.intelligence_query_var.get()
        assert "内置技术词典" in app.intelligence_preview.get("1.0", "end")
        app.intelligence_query_var.set("pilot valve")
        send_to_search(app)
        assert app.search_query_var.get() == "pilot valve"
        assert app._pages["search"].winfo_manager() == "pack"
        app.intelligence_workflow_var.set("专利全景分析")
        run_task(app)
        assert "本地库尚无已索引公开件" in app.intelligence_preview.get("1.0", "end")
        runtime.library_store.upsert_publication(
            PatentPublication(
                publication_number="US20240000001A1",
                jurisdiction="US",
                title="Suspension damper pilot valve",
            )
        )
        app._intelligence_report = AnalysisService(runtime.library_store).landscape(AnalysisScope())
        copy_ai_prompt(app)
        assert "只基于列出的数据" in app.clipboard_get()
        errors = []
        monkeypatch.setattr(
            "app.desktop.intelligence_tab.messagebox.showerror", lambda *args: errors.append(args)
        )
        run_task(app)
        deadline = time.monotonic() + 3
        while app._intelligence_report is None and not errors and time.monotonic() < deadline:
            app.update()
            time.sleep(0.01)
        assert not errors
        assert app._intelligence_report is not None
        assert app._intelligence_report.workflow == "landscape"
    finally:
        app._on_close()


def test_desktop_uses_chinese_navigation_and_evidence_filters(tmp_path, monkeypatch):
    runtime = DesktopRuntime.create(paths=AppPaths.for_root(tmp_path / "appdata"))
    app = PatentWorkbenchApp(runtime)
    app.withdraw()
    try:
        assert app.title() == "专利情报工作台"
        assert app._nav_buttons["search"].cget("text") == "⌕   专利检索"
        assert app._nav_buttons["library"].cget("text") == "▤   本地专利库"
        assert app.evidence_type_var.get() == "全部类型"

        captured = {}
        monkeypatch.setattr(
            runtime.library_store,
            "list_evidence",
            lambda **kwargs: captured.update(kwargs) or (),
        )
        app.evidence_type_var.set("网页")
        app.refresh_evidence()
        assert captured["source_type"] == "url"
    finally:
        app._on_close()
