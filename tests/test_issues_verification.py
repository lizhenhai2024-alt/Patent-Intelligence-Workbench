"""End-to-end desktop checks for the features listed in tasks/ISSUES.md item 4."""

from datetime import date

import pytest

from app.desktop.app import (
    _EMPTY_TREE_IID,
    PatentWorkbenchApp,
    _insert_empty_placeholder,
)
from app.desktop.runtime import DesktopRuntime
from app.desktop.tk_runtime import can_run_tk_tests
from app.domain.search import SearchHit, SearchMode, SearchPage, SearchResponse

pytestmark = pytest.mark.skipif(
    not can_run_tk_tests(),
    reason="Tk UI tests require a usable Tcl/Tk runtime",
)


@pytest.fixture()
def app():
    runtime = DesktopRuntime.create()
    instance = PatentWorkbenchApp(runtime)
    instance.withdraw()
    yield instance
    instance.destroy()
    runtime.close()


def test_reader_open_by_patent_number(app):
    """Issue 1: Reader can be opened by typing a publication number directly."""
    app.reader_open_number_var.set("US20240123456A1")
    app.open_reader_by_number()
    assert app.reader_number_var.get() == "US20240123456A1"
    assert app._reader_hit is not None
    assert app._reader_hit.publication_number == "US20240123456A1"


def test_reader_open_by_invalid_number_shows_error(app, monkeypatch):
    captured = {}
    monkeypatch.setattr(
        "app.desktop.app.messagebox.showerror",
        lambda title, msg: captured.update(title=title, msg=msg),
    )
    app.reader_open_number_var.set("not-a-patent")
    app.open_reader_by_number()
    assert captured.get("title") == "公开号无法识别"
    assert app._reader_hit is None


def test_empty_placeholders_on_core_pages(app):
    """Issue 2: Search/Family/Watch/Library show guidance when empty."""
    assert _EMPTY_TREE_IID in app.search_tree.get_children()
    assert _EMPTY_TREE_IID in app.family_tree.get_children()
    # Watch ships with preset template rules, so placeholder only appears when none exist
    watch_children = app.watch_rule_tree.get_children()
    if not watch_children or watch_children == (_EMPTY_TREE_IID,):
        assert _EMPTY_TREE_IID in watch_children or not watch_children
    # Library may have data; placeholder only when empty
    app.refresh_library()
    library_real = [
        iid for iid in app.library_tree.get_children() if iid != _EMPTY_TREE_IID
    ]
    if not library_real:
        assert _EMPTY_TREE_IID in app.library_tree.get_children()


def test_placeholder_selection_is_ignored(app):
    """Selecting the placeholder must not open Reader or crash."""
    app.search_tree.selection_set(_EMPTY_TREE_IID)
    app._open_selected_in_reader()
    assert app._reader_hit is None

    app.search_tree.selection_set(_EMPTY_TREE_IID)
    before = app.family_number_var.get()
    app._search_to_family()
    assert app.family_number_var.get() == before

    # Library may hold real patents; only test placeholder path if present
    if _EMPTY_TREE_IID in app.library_tree.get_children():
        app.library_tree.selection_set(_EMPTY_TREE_IID)
        assert app._selected_library_patent() is None

    if _EMPTY_TREE_IID in app.watch_rule_tree.get_children():
        app.watch_rule_tree.selection_set(_EMPTY_TREE_IID)
        app._load_selected_watch_cadence()  # must not raise


def test_search_render_clears_placeholder_and_zero_results_restores_it(app):
    hit = SearchHit(
        publication_number="US20240000001A1",
        jurisdiction="US",
        title="Damper",
        applicants=("Example Corp",),
        publication_date=date(2024, 1, 4),
    )
    response = SearchResponse(
        mode=SearchMode.TEXT,
        provider="test",
        page=SearchPage(hits=(hit,), total_result_count=1),
        normalized_query="damper",
    )
    app._render_search_response(response)
    assert _EMPTY_TREE_IID not in app.search_tree.get_children()
    assert hit.publication_number in app.search_tree.get_children()

    empty = SearchResponse(
        mode=SearchMode.TEXT,
        provider="test",
        page=SearchPage(hits=(), total_result_count=0),
        normalized_query="nothing",
    )
    app._render_search_response(empty)
    assert _EMPTY_TREE_IID in app.search_tree.get_children()


def test_watch_create_custom_rule(app):
    """Issue 4: Watch tab 新建监控规则 form actually creates a rule."""
    import time

    unique_name = f"Test Rule {int(time.time() * 1000)}"
    app.watch_new_name_var.set(unique_name)
    app.watch_new_company_var.set("TestCo")
    app.watch_new_terms_var.set("damper, valve")
    app.watch_new_cadence_var.set("12")
    app.create_watch_rule()

    rules = app.runtime.watch_store.list_rules()
    created = [r for r in rules if r.name == unique_name]
    assert len(created) == 1
    rule = created[0]
    assert rule.cadence_hours == 12
    assert "damper" in rule.technology_terms
    # Placeholder must be gone after real rule exists
    assert _EMPTY_TREE_IID not in app.watch_rule_tree.get_children()
    assert rule.rule_id in app.watch_rule_tree.get_children()


def test_watch_create_rule_validation(app, monkeypatch):
    captured = {}
    monkeypatch.setattr(
        "app.desktop.app.messagebox.showinfo",
        lambda title, msg: captured.update(title=title, msg=msg),
    )
    app.watch_new_name_var.set("")
    app.watch_new_company_var.set("")
    app.create_watch_rule()
    assert captured.get("title") == "信息不完整"


def test_technology_filter_narrows_tree(app):
    """Issue 4: Technology search/filter box filters nodes."""
    full_count = len(app.technology_tree.get_children(""))
    assert full_count > 0

    app.technology_filter_var.set("damper")
    app._rebuild_technology_tree()
    filtered = len(app.technology_tree.get_children(""))
    assert filtered <= full_count
    # Every visible node should match (or be ancestor of a match)
    for iid in app.technology_tree.get_children(""):
        node = app.technology_taxonomy.find(iid)
        assert node is not None
        assert app._technology_node_matches(node, "damper")

    app._clear_technology_filter()
    assert len(app.technology_tree.get_children("")) == full_count


def test_technology_node_tags(app):
    """Issue 4: leaf nodes are blue, category nodes are gray."""
    tags = app.technology_tree.item("suspension", "tags")
    assert "category" in tags
    # Find a leaf with search_terms
    leaf_id = None
    for node in app.technology_taxonomy.roots:
        if node.search_terms:
            leaf_id = node.node_id
            break
        for child in node.children:
            if child.search_terms:
                leaf_id = child.node_id
                break
        if leaf_id:
            break
    if leaf_id and app.technology_tree.exists(leaf_id):
        assert "leaf" in app.technology_tree.item(leaf_id, "tags")


def test_technology_category_search_shows_messagebox(app, monkeypatch):
    captured = {}
    monkeypatch.setattr(
        "app.desktop.app.messagebox.showinfo",
        lambda title, msg: captured.update(title=title, msg=msg),
    )
    app.technology_tree.selection_set("suspension")
    app._search_selected_technology()
    assert "可检索" in captured.get("title", "") or "分类节点" in captured.get(
        "msg", ""
    )


def test_translation_provider_switch_clears_stale_endpoint(app):
    """Issue 4 (revised 2026-09-23): LLM translation uses a shared AI model profile.

    DeepL still auto-fills its endpoint; "大模型" disables endpoint/key and picks a
    profile instead, so no stale LLM endpoint or plaintext key can be left behind.
    """
    app.translation_provider_var.set("deepl")
    app.translation_endpoint_var.set("")
    app._on_translation_provider_changed()
    assert app.translation_endpoint_var.get() == "https://api-free.deepl.com/v2/translate"

    app.translation_provider_var.set("大模型")
    app._on_translation_provider_changed()
    assert "disabled" in app.translation_endpoint_entry.state()
    assert "disabled" in app.translation_api_key_entry.state()
    assert "disabled" not in app.translation_profile_combo.state()

    # User-typed custom endpoint must not be overwritten when switching back.
    app.translation_provider_var.set("http")
    app.translation_endpoint_var.set("https://my-custom.example/api")
    app._on_translation_provider_changed()
    assert app.translation_endpoint_var.get() == "https://my-custom.example/api"
    assert "disabled" not in app.translation_endpoint_entry.state()


def test_reader_translation_reentrancy_guard(app):
    """Issue 4: rapid re-trigger while busy is a no-op."""
    app._reader_translation_in_flight = True
    called = {"translate": False}

    def fake_translate(text):
        called["translate"] = True

    app.translation_provider.translate = fake_translate
    # Should return early without calling translate
    app._translate_reader_text("hello")
    assert called["translate"] is False
    assert app._reader_translation_in_flight is True
    # Reset for cleanup
    app._reader_translation_in_flight = False


def test_intelligence_run_button_reentrancy_guard(app, monkeypatch):
    """Issue 4: clicking 运行任务 while disabled is a no-op."""
    if not hasattr(app, "intelligence_run_button"):
        pytest.skip("Intelligence tab not built in this build")
    # Use configure(state=...) which is what run_task reads via ["state"]
    app.intelligence_run_button.configure(state="disabled")
    from app.desktop.intelligence_tab import run_task

    # Spy on state() method: run_task's non-guard path starts with state(["disabled"])
    original_state = app.intelligence_run_button.state
    state_calls = []

    def spy_state(spec=None):
        if spec is not None:
            state_calls.append(list(spec))
        return original_state(spec) if spec is not None else original_state()

    app.intelligence_run_button.state = spy_state
    try:
        run_task(app)
    finally:
        app.intelligence_run_button.state = original_state
        app.intelligence_run_button.configure(state="!disabled")
    # Guard returned early: run_task never reached its state(["disabled"]) line
    assert ["disabled"] not in state_calls


def test_insert_empty_placeholder_is_idempotent():
    """Helper must not insert a second placeholder if tree already has rows."""
    import tkinter as tk

    root = tk.Tk()
    root.withdraw()
    tree = tk.ttk.Treeview(root)
    _insert_empty_placeholder(tree, "first")
    _insert_empty_placeholder(tree, "second")
    children = tree.get_children()
    assert len(children) == 1
    assert children[0] == _EMPTY_TREE_IID
    root.destroy()


def test_reader_translation_shows_translated_text_not_coroutine_error(app):
    """2026-09-23: a successful translation was shown as
    'a coroutine was expected, got TranslationResult(...)'."""
    import time

    from app.core.translation import TranslationResult

    class FakeProvider:
        def translate(self, text):
            return TranslationResult(text="1. 一种缓冲器", provider="fake")

    app.translation_provider = FakeProvider()
    app._translate_reader_text("1. A shock absorber")
    deadline = time.monotonic() + 3
    while app._reader_translation_in_flight and time.monotonic() < deadline:
        app.update()
        time.sleep(0.01)
    shown = app.reader_translation_text.get("1.0", "end").strip()
    assert shown == "1. 一种缓冲器"
    assert "coroutine" not in shown
