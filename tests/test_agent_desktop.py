import json
import threading
import time

import pytest

from app.agents.model_profiles import MemorySecretStore
from app.agents.receipts import check_answer
from app.agents.runtime import AgentResult, CheckpointDecision
from app.desktop.paths import AppPaths
from app.desktop.tk_runtime import can_run_tk_tests

pytestmark = pytest.mark.skipif(
    not can_run_tk_tests(), reason="Tk UI tests require a usable Tcl/Tk runtime"
)

KEY = "sk-DESKTOP-SECRET"


@pytest.fixture
def app(tmp_path, monkeypatch):
    monkeypatch.setattr("app.desktop.agent_tab.ai_secret_store", MemorySecretStore)
    from app.desktop.app import PatentWorkbenchApp
    from app.desktop.runtime import DesktopRuntime

    runtime = DesktopRuntime.create(paths=AppPaths.for_root(tmp_path / "appdata"))
    application = PatentWorkbenchApp(runtime)
    application.withdraw()
    yield application
    application.destroy()


def _pump(app, predicate, seconds=3.0):
    deadline = time.monotonic() + seconds
    while not predicate() and time.monotonic() < deadline:
        app.update()
        time.sleep(0.01)
    assert predicate()


def test_agents_page_presets_and_profile_without_key_on_disk(app, tmp_path):
    from app.desktop.agent_tab import apply_preset, save_profile

    app._show_page("agents")
    assert "本地库问答（演示）" in app.agent_choice_combo["values"]
    app.agent_preset_var.set("小米 MiMo（按量付费，sk- Key）")
    apply_preset(app)
    assert app.agent_base_url_var.get() == "https://api.xiaomimimo.com/v1"
    assert app.agent_auth_var.get() == "api-key"
    assert app.agent_model_var.get() == "mimo-v2.6-flash"
    app.agent_key_var.set(KEY)
    save_profile(app)
    stored = (tmp_path / "appdata" / "model_profiles.json").read_text(encoding="utf-8")
    assert "小米 MiMo" in json.loads(stored)["profiles"][0]["name"]
    assert KEY not in stored
    assert app.agent_key_var.get() == ""
    assert "已保存" in app.agent_key_status_var.get()


def test_run_shows_flagged_lines_without_a_consent_popup(app, monkeypatch):
    from app.desktop import agent_tab

    app.agent_preset_var.set("DeepSeek 深度求索")
    agent_tab.apply_preset(app)
    app.agent_model_var.set("deepseek-chat")
    app.agent_key_var.set(KEY)
    agent_tab.save_profile(app)
    app.agent_question.insert("1.0", "KYB 的阀？")

    runs = []

    class FakeRunner:
        def __init__(self, definition, profile, api_key, tools, **kwargs):
            self.kwargs = kwargs
            runs.append(api_key)

        def run(self, question):
            decision = self.kwargs["on_checkpoint"]("search_terms", "阀")
            text = "- 先导阀 [CN1A]\n- 无引用\n" + ("- 确认:" + decision.payload)
            return AgentResult("completed", text, check_answer(text, {"CN1A"}), 2, ("CN1A",), None)

    monkeypatch.setattr(agent_tab, "AgentRunner", FakeRunner)
    asked = []
    monkeypatch.setattr(agent_tab.messagebox, "askyesno", lambda *a, **k: asked.append(a))
    assert "api.deepseek.com" in app.agent_send_notice_var.get()
    agent_tab.run_agent(app)
    assert asked == []  # no per-run popup; the standing notice replaces it
    _pump(app, lambda: getattr(app, "_agent_checkpoint_dialog", None) is not None)
    dialog = app._agent_checkpoint_dialog
    text_widget = next(w for w in dialog.winfo_children() if w.winfo_class() == "Text")
    text_widget.delete("1.0", "end")
    text_widget.insert("1.0", "先导阀")
    confirm = [
        b for frame in dialog.winfo_children() for b in frame.winfo_children()
        if b.winfo_class() == "TButton" and b.cget("text") == "确认"
    ][0]
    confirm.invoke()
    _pump(app, lambda: "状态" in app.agent_banner_var.get())
    output = app.agent_output.get("1.0", "end")
    assert runs == [KEY]
    assert "⚠ 无证据支撑" in output
    assert "确认:先导阀" in output
    assert "需复核的行 2" in app.agent_banner_var.get()
    assert str(app.agent_run_button["state"]) != "disabled"


def test_cancel_releases_a_pending_checkpoint(app):
    from app.desktop import agent_tab

    result = {}

    def worker():
        result["decision"] = agent_tab._checkpoint_from_worker(app, "final", "草稿")

    thread = threading.Thread(target=worker)
    thread.start()
    _pump(app, lambda: getattr(app, "_agent_checkpoint_dialog", None) is not None)
    agent_tab.cancel_agent(app)
    thread.join(timeout=2)
    assert result["decision"] == CheckpointDecision(False)


def test_switching_preset_never_reuses_another_providers_key(app, monkeypatch):
    from app.desktop import agent_tab

    app.agent_preset_var.set("小米 MiMo（按量付费，sk- Key）")
    agent_tab.apply_preset(app)
    app.agent_key_var.set(KEY)
    agent_tab.save_profile(app)
    # Pick another preset: the default name follows the preset, the key field is cleared.
    app.agent_preset_var.set("DeepSeek 深度求索")
    agent_tab.apply_preset(app)
    assert app.agent_profile_name_var.get() == "DeepSeek 深度求索"
    assert app.agent_key_var.get() == ""
    # Forcing the old name onto a new endpoint without a new key is refused.
    app.agent_profile_name_var.set("小米 MiMo（按量付费，sk- Key）")
    app.agent_model_var.set("deepseek-chat")
    shown = []
    monkeypatch.setattr(agent_tab.messagebox, "showinfo", lambda *args: shown.append(args))
    agent_tab.save_profile(app)
    assert shown and "接口地址变了" in shown[0][1]
    assert app._agent_profiles.get("小米 MiMo（按量付费，sk- Key）").base_url == "https://api.xiaomimimo.com/v1"


def test_model_is_chosen_from_a_readonly_dropdown_filled_by_get_models(app, monkeypatch):
    from app.desktop import agent_tab

    assert str(app.agent_model_combo.cget("state")) == "readonly"
    app.agent_preset_var.set("通义千问 Qwen")
    agent_tab.apply_preset(app)
    assert app.agent_model_var.get() == ""
    assert "获取模型列表" in app.agent_key_status_var.get()
    calls = []

    def fake_fetch(base_url, auth_style, api_key):
        calls.append((base_url, auth_style, api_key))
        return ("qwen-max", "qwen-plus")

    monkeypatch.setattr(agent_tab, "fetch_models", fake_fetch)
    app.agent_key_var.set(KEY)
    agent_tab.fetch_model_list(app)
    _pump(app, lambda: tuple(app.agent_model_combo["values"]) == ("qwen-max", "qwen-plus"))
    assert calls == [("https://dashscope.aliyuncs.com/compatible-mode/v1", "bearer", KEY)]
    assert app.agent_model_var.get() == "qwen-max"


def test_intelligence_ai_interpretation_uses_shared_model_profile(app, monkeypatch):
    from app.agents.model_profiles import ModelProfile
    from app.desktop import intelligence_tab
    from app.desktop.agent_tab import refresh_profiles
    from app.intelligence.analysis import AnalysisScope, AnalysisService

    profile = ModelProfile(
        "小米 MiMo Token Plan（tp- Key）",
        "mimo_tp_cn",
        "https://token-plan-cn.xiaomimimo.com/v1",
        "api-key",
        "mimo-v2.6-flash",
    )
    app.model_profiles.save(profile, "tp-SECRET")
    refresh_profiles(app)
    assert app.intelligence_ai_profile_var.get() == profile.name
    assert not hasattr(app, "intelligence_ai_key_var")  # no separate key entry any more

    captured = {}

    class FakeInterpreter:
        def __init__(self, settings):
            captured["settings"] = settings

        def interpret(self, report):
            return "ok"

    monkeypatch.setattr(intelligence_tab, "OpenAICompatibleInterpreter", FakeInterpreter)
    app._intelligence_report = AnalysisService(app.runtime.library_store).landscape(
        AnalysisScope()
    )
    assert not hasattr(app, "intelligence_ai_consent_var")  # no checkbox any more
    intelligence_tab.run_ai_interpretation(app)
    _pump(app, lambda: "settings" in captured)
    settings = captured["settings"]
    assert settings.endpoint == "https://token-plan-cn.xiaomimimo.com/v1/chat/completions"
    assert settings.auth_style == "api-key"
    assert settings.api_key == "tp-SECRET"
    assert settings.model == "mimo-v2.6-flash"
