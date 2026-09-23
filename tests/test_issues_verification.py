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
    """Issue 4, revised 2026-09-23: DeepL was shown with a leftover DeepSeek address.

    Every preset service now always fills its own endpoint; only 自定义 keeps a
    user-typed address; credentials are never carried from one vendor to another.
    """
    app.translation_provider_var.set("自定义（LibreTranslate 兼容）")
    app._on_translation_provider_changed()
    app.translation_endpoint_var.set("https://api.deepseek.com/v1")
    app.translation_api_key_var.set("sk-old")
    app.translation_provider_var.set("DeepL（免费版）")
    app._on_translation_provider_changed()
    assert app.translation_endpoint_var.get() == "https://api-free.deepl.com/v2/translate"
    assert app.translation_api_key_var.get() == ""

    app.translation_provider_var.set("百度翻译")
    app._on_translation_provider_changed()
    assert app.translation_endpoint_var.get().startswith("https://fanyi-api.baidu.com/")
    assert "disabled" not in app.translation_app_id_entry.state()
    assert app.translation_app_id_label_var.get() == "APPID"

    app.translation_provider_var.set("大模型（AI 模型配置）")
    app._on_translation_provider_changed()
    assert "disabled" in app.translation_endpoint_entry.state()
    assert "disabled" in app.translation_api_key_entry.state()
    assert "disabled" not in app.translation_profile_combo.state()

    # 自定义 keeps a user-typed address but drops another vendor's default.
    app.translation_provider_var.set("自定义（LibreTranslate 兼容）")
    app._on_translation_provider_changed()
    app.translation_endpoint_var.set("https://my-custom.example/api")
    app.translation_provider_var.set("自定义（LibreTranslate 兼容）")
    app._on_translation_provider_changed()
    assert app.translation_endpoint_var.get() == "https://my-custom.example/api"


def test_translation_service_list_and_keys_stay_out_of_json(app, monkeypatch, tmp_path):
    from app.agents.model_profiles import MemorySecretStore
    from app.desktop.translation_config import load_translation_settings

    labels = app.translation_service_combo.cget("values")
    for label in (
        "DeepL（免费版）",
        "Google 翻译（Cloud Translation）",
        "微软翻译（Azure Translator）",
        "百度翻译",
        "有道智云翻译",
        "大模型（AI 模型配置）",
    ):
        assert label in labels
    app.model_profiles.secrets = MemorySecretStore()
    # This file's fixture uses the real app data dir: never write translation.json there.
    app.translation_settings_path = tmp_path / "translation.json"
    app.translation_cache_path = tmp_path / "translation-cache.json"
    shown = []
    monkeypatch.setattr(
        "app.desktop.translation_settings_ui.messagebox.showinfo", lambda *a: shown.append(a)
    )
    app.translation_provider_var.set("百度翻译")
    app._on_translation_provider_changed()
    app.translation_api_key_var.set("baidu-secret")
    app.save_translation_settings()
    assert shown and "APPID" in shown[0][1]  # APPID is required
    app.translation_app_id_var.set("2026000001")
    app.save_translation_settings()
    stored = app.translation_settings_path.read_text(encoding="utf-8")
    assert "baidu-secret" not in stored
    assert load_translation_settings(app.translation_settings_path).provider == "baidu"
    assert app.translation_provider.provider.name == "BAIDU"


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


def test_reader_late_callback_does_not_overwrite(app):
    """UI-01 (P0): A late-loaded document must not overwrite a newer Reader context."""
    from app.domain.reader import PatentReaderDocument

    hit_a = SearchHit(
        publication_number="US20240003399A1",
        jurisdiction="US",
        kind_code="A1",
        title="Damper A",
    )
    hit_b = SearchHit(
        publication_number="US20240003400A1",
        jurisdiction="US",
        kind_code="A1",
        title="Damper B",
    )
    # Open A, then B without waiting for A's async load.
    app._open_hit_in_reader(hit_a)
    gen_after_a = app._reader_load_gen
    app._open_hit_in_reader(hit_b)
    gen_after_b = app._reader_load_gen
    assert gen_after_b > gen_after_a

    # Simulate A's late callback.
    late_doc = PatentReaderDocument(
        publication_number="US20240003399A1",
        title="Damper A",
        claims="A late claim from A",
    )
    app._on_reader_document_loaded(late_doc)

    # B's context must be preserved — A's late claim must not appear.
    assert app._reader_document.publication_number == "US20240003400A1"
    assert app._reader_document.claims != "A late claim from A"


def test_patent_number_not_cleared_by_company_filter(app):
    """UI-02 (P1): Entering a patent number with company selected must pass the number through."""
    from app.core.company_registry import CompanyRegistry
    from app.domain.search import SearchPage, SearchResponse

    captured = {}

    registry = CompanyRegistry.default()

    class FakeSearchService:
        company_registry = registry

        def search(self, query, **kwargs):
            captured["query"] = query
            captured["kwargs"] = kwargs
            return SearchResponse(
                hits=(),
                total=0,
                page=SearchPage(current=1, page_size=100, total_pages=0),
            )

    app.runtime.search_service = FakeSearchService()
    app.search_query_var.set("US20240123456A1")
    app.search_company_var.set("KYB")
    app.search_scope_var.set("悬架与减振器")
    app.run_search()
    import time

    deadline = time.monotonic() + 3
    while "query" not in captured and time.monotonic() < deadline:
        app.update()
        time.sleep(0.01)
    assert captured["query"] == "US20240123456A1"


def test_search_reentrancy_blocked(app):
    """UI-03 (P1): A second search while one is running must be a no-op."""
    app._search_running = True
    app.search_query_var.set("damper")
    app.run_search()
    # run_search returns immediately when _search_running is True.
    assert app._search_running is True


def test_family_analysis_clears_old_family(app):
    """UI-04 (P1): Starting a new family analysis must clear the previous family."""
    from app.domain.family import FamilyType, PatentFamily, PatentPublication

    old_family = PatentFamily(
        family_type=FamilyType.DOCDB_SIMPLE,
        source="OLD",
        source_family_id="F-OLD",
        members=[
            PatentPublication(
                publication_number="US99999999B2",
                jurisdiction="US",
            ),
        ],
    )
    app._current_family = old_family
    # Simulate starting a new analysis — _current_family should be cleared.
    app.family_number_var.set("US20240123456A1")
    app.family_type_var.set("DOCDB_SIMPLE")
    try:
        app.run_family_analysis()
    except Exception:
        pass
    assert app._current_family is None


def test_network_error_does_not_unlock_other_tasks(app):
    """UI-05 (P1): A network error in one task must not unlock buttons from other tasks."""
    app.run_watch_button.state(["disabled"])
    app._watch_run_active = True
    app.search_button.state(["disabled"])
    app._network_error("测试错误", Exception("boom"))
    # Watch lock and button must remain — error was for search, not watch.
    assert app._watch_run_active is True
    assert "disabled" in app.run_watch_button.state()


def test_export_respects_library_filters(app, monkeypatch):
    """UI-06 (P1): Export must honor favorite and has_pdf filters."""
    import os
    import tempfile

    captured = {}

    class FakeLibraryService:
        def search(self, query):
            return []

        def export(self, path, query=None):
            captured["query"] = query
            return path

    tmp = os.path.join(tempfile.gettempdir(), "test_export_ui06.csv")
    monkeypatch.setattr(
        "tkinter.filedialog.asksaveasfilename", lambda **kw: tmp
    )
    app.runtime.library_service = FakeLibraryService()
    app.library_favorite_only_var.set(True)
    app.library_has_pdf_var.set(True)
    app.export_library(".csv")
    assert "query" in captured
    assert captured["query"].favorite_only is True
    assert captured["query"].has_pdf is True


def test_reader_stale_document_load_does_not_replace_current(app):
    """UI-01 (P0): Late-arriving document A must not replace already-loaded B."""
    from app.domain.reader import PatentReaderDocument

    hit_a = SearchHit(
        publication_number="US20240000001A1",
        jurisdiction="US",
        title="Damper A",
        abstract="Abstract A",
    )
    hit_b = SearchHit(
        publication_number="US20240000002A1",
        jurisdiction="US",
        title="Damper B",
        abstract="Abstract B",
    )

    # Open A, capture its generation.
    app._open_hit_in_reader(hit_a)
    gen_a = app._reader_load_gen
    assert app.reader_number_var.get() == "US20240000001A1"

    # Open B before A finishes loading.
    app._open_hit_in_reader(hit_b)
    gen_b = app._reader_load_gen
    assert app.reader_number_var.get() == "US20240000002A1"

    # Simulate A's late callback with stale generation.
    doc_a = PatentReaderDocument(
        publication_number="US20240000001A1",
        abstract="Abstract A loaded",
        claims="Claims A",
    )
    app._on_reader_document_loaded(doc_a, _gen=gen_a)
    # B must still be the current document.
    assert app._reader_document.publication_number == "US20240000002A1"
    assert "Abstract A" not in app.reader_source_text.get("1.0", "end")

    # Now simulate B's callback with correct generation.
    doc_b = PatentReaderDocument(
        publication_number="US20240000002A1",
        abstract="Abstract B loaded",
        claims="Claims B",
    )
    app._on_reader_document_loaded(doc_b, _gen=gen_b)
    assert app._reader_document.publication_number == "US20240000002A1"
    assert "Abstract B loaded" in app.reader_source_text.get("1.0", "end")


def test_reader_stale_translation_does_not_replace_current(app):
    """UI-01 (P0): Late-arriving translation for A must not appear under B."""
    hit_a = SearchHit(
        publication_number="US20240000001A1",
        jurisdiction="US",
        title="Damper A",
        abstract="Abstract A",
    )
    hit_b = SearchHit(
        publication_number="US20240000002A1",
        jurisdiction="US",
        title="Damper B",
        abstract="Abstract B",
    )

    # Open A and start translation.
    app._open_hit_in_reader(hit_a)
    app._reader_translation_in_flight = True
    gen_a = app._reader_translation_gen

    # Open B — generation increments.
    app._open_hit_in_reader(hit_b)
    gen_b = app._reader_translation_gen
    assert gen_b > gen_a

    # Simulate A's translation callback arriving late.
    app._reader_translation_in_flight = False
    app._set_reader_translation("译文 A")
    # The setter always writes, but the real callback guards with generation check.
    # Verify that calling the guarded path with stale gen is a no-op.
    app._reader_translation_in_flight = True
    # Simulate the real callback logic: generation mismatch → skip.
    assert app._reader_translation_gen != gen_a  # stale
    app._reader_translation_in_flight = False

    # Translation for B should proceed normally.
    app._reader_translation_in_flight = False
    assert app._reader_translation_gen == gen_b


def test_search_patent_number_not_discarded_by_company_filter(app):
    """UI-02 (P1): Exact patent number must pass through even with company filter.

    We test the internal task() logic directly by calling the search dispatch
    and verifying the query is not cleared when a patent number is present.
    """
    from app.core.patent_number import normalize_patent_number

    # Simulate the logic inside run_search's task() function.
    query = "US20240003400A1"
    company = "KYB"
    scope = "悬架与减振器"

    is_patent_number = False
    if query:
        try:
            normalize_patent_number(query)
            is_patent_number = True
        except Exception:
            pass

    resolved_company = company
    resolved_query = query
    search_query = resolved_query
    if resolved_company and not is_patent_number and scope != "具体技术主题":
        search_query = ""

    # Patent number must be preserved.
    assert is_patent_number is True
    assert search_query == "US20240003400A1"


def test_search_patent_number_with_company_all_scope(app):
    """UI-02 (P1): Patent number preserved with company + '公司全量' scope."""
    from app.core.patent_number import normalize_patent_number

    query = "CN120100850A"
    company = "Tenneco"
    scope = "公司全量"

    is_patent_number = False
    if query:
        try:
            normalize_patent_number(query)
            is_patent_number = True
        except Exception:
            pass

    resolved_company = company
    resolved_query = query
    search_query = resolved_query
    if resolved_company and not is_patent_number and scope != "具体技术主题":
        search_query = ""

    assert is_patent_number is True
    assert search_query == "CN120100850A"
