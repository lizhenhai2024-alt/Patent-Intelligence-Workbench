"""Desktop page for bounded agents (Agent track M2), plus the shared AI model
profiles section shown in Settings (used by agents and LLM translation).

Worker threads never touch Tk: progress, checkpoints and results are marshalled
through ``app._ui_callbacks``.
"""

from __future__ import annotations

import threading
import tkinter as tk
from tkinter import messagebox, ttk

from app.agent_tools.tools import open_read_only
from app.agents.definition import AgentDefinition, load_definitions
from app.agents.model_profiles import (
    ModelProfile,
    ProfileStore,
    fetch_models,
    key_mismatch_hint,
    load_presets,
)
from app.agents.render import blocks, render_html, text_parts
from app.agents.runtime import AgentResult, AgentRunner, CheckpointDecision
from app.desktop.cards import Card
from app.desktop.credentials import ai_secret_store
from app.desktop.opening import open_local_path

_STATUS_TEXT = {
    "completed": "完成",
    "step_limit": "达到步数上限，结果不完整",
    "cancelled": "已取消",
    "error": "出错",
}
_CHECKPOINT_TITLES = {
    "search_terms": ("确认检索词", "智能体准备使用以下检索词（每行一个），可修改后确认："),
    "final": ("确认最终回答", "请审阅智能体的回答，可修改后确认显示："),
}


def init_model_profiles(app) -> None:
    """Shared by the Agents page, Settings and LLM translation; call before building pages."""
    paths = app.runtime.paths
    app.model_profiles = ProfileStore(paths.root / "model_profiles.json", ai_secret_store())
    app._agent_profiles = app.model_profiles
    app._agent_presets = {preset.name: preset for preset in load_presets()}


def build_agent_tab(app) -> None:
    page = app.agent_tab
    ttk.Label(page, text="专利情报智能体", style="PageTitle.TLabel").pack(anchor="w")
    ttk.Label(
        page,
        text="智能体只读查询本地库；每条结论须引用本次查到的公开号，无依据的行会被标出",
        style="Subtle.TLabel",
    ).pack(anchor="w", pady=(2, 12))

    if not hasattr(app, "model_profiles"):
        init_model_profiles(app)
    paths = app.runtime.paths
    app._agent_log_dir = paths.root / "agent_runs"
    app._agent_user_dir = paths.root / "agents"
    app._agent_cancel: threading.Event | None = None
    app._agent_pending_checkpoint: tuple[dict, threading.Event] | None = None
    app._agent_last_log = None

    _build_run_section(app, page)
    _build_result_section(app, page)
    reload_agents(app)
    refresh_profiles(app)


# -- model profiles ------------------------------------------------------------


def build_model_profiles_section(app, parent, **pack_options) -> None:
    """Settings section: create/edit the AI model profiles shared by agents and translation."""
    box = ttk.LabelFrame(parent, text="AI 模型配置（智能体和大模型翻译共用）", padding=12)
    box.pack(fill="x", **pack_options)
    app.agent_profile_var = tk.StringVar()
    app.agent_preset_var = tk.StringVar()
    app.agent_profile_name_var = tk.StringVar()
    app.agent_base_url_var = tk.StringVar()
    app.agent_auth_var = tk.StringVar(value="bearer")
    app.agent_model_var = tk.StringVar()
    app.agent_key_var = tk.StringVar()
    app.agent_key_status_var = tk.StringVar()

    top = ttk.Frame(box)
    top.pack(fill="x")
    ttk.Label(top, text="已保存的配置").pack(side="left")
    app.agent_profile_combo = ttk.Combobox(
        top, textvariable=app.agent_profile_var, state="readonly", width=28
    )
    app.agent_profile_combo.pack(side="left", padx=6)
    app.agent_profile_combo.bind("<<ComboboxSelected>>", lambda _e: load_profile(app))
    ttk.Label(top, text="厂商预设").pack(side="left", padx=(16, 0))
    preset_combo = ttk.Combobox(
        top,
        textvariable=app.agent_preset_var,
        values=list(app._agent_presets),
        state="readonly",
        width=24,
    )
    preset_combo.pack(side="left", padx=6)
    preset_combo.bind("<<ComboboxSelected>>", lambda _e: apply_preset(app))

    form = ttk.Frame(box)
    form.pack(fill="x", pady=(8, 0))
    fields = (
        ("配置名称", lambda cell: ttk.Entry(cell, textvariable=app.agent_profile_name_var)),
        ("接口地址", lambda cell: ttk.Entry(cell, textvariable=app.agent_base_url_var)),
        (
            "认证方式",
            lambda cell: ttk.Combobox(
                cell,
                textvariable=app.agent_auth_var,
                values=["bearer", "api-key"],
                state="readonly",
            ),
        ),
        (
            "模型（下拉选择）",
            lambda cell: ttk.Combobox(cell, textvariable=app.agent_model_var, state="readonly"),
        ),
        ("API Key", lambda cell: ttk.Entry(cell, textvariable=app.agent_key_var, show="*")),
    )
    widgets = []
    for index, (label, make) in enumerate(fields):
        row, col = divmod(index, 3)
        cell = ttk.Frame(form)
        cell.grid(row=row, column=col, sticky="ew", padx=(0, 12), pady=3)
        ttk.Label(cell, text=label).pack(anchor="w")
        widget = make(cell)
        widget.pack(fill="x")
        widgets.append(widget)
        form.columnconfigure(col, weight=1)
    app.agent_model_combo = widgets[3]

    actions = ttk.Frame(box)
    actions.pack(fill="x", pady=(6, 0))
    app.agent_fetch_models_button = ttk.Button(
        actions, text="获取模型列表", command=lambda: fetch_model_list(app)
    )
    app.agent_fetch_models_button.pack(side="left")
    ttk.Button(actions, text="保存配置", command=lambda: save_profile(app)).pack(
        side="left", padx=8
    )
    ttk.Button(actions, text="删除配置", command=lambda: delete_profile(app)).pack(
        side="left", padx=8
    )
    ttk.Label(actions, textvariable=app.agent_key_status_var, style="Subtle.TLabel").pack(
        side="left", padx=8
    )


def apply_preset(app) -> None:
    preset = app._agent_presets.get(app.agent_preset_var.get())
    if preset is None:
        return
    app.agent_base_url_var.set(preset.base_url)
    app.agent_auth_var.set(preset.auth_style)
    _set_model_choices(app, preset.suggested_models)
    if not preset.suggested_models:
        app.agent_key_status_var.set("该厂商没有内置模型清单：填入 API Key 后点“获取模型列表”")
    # A name still equal to another preset's default would silently overwrite that profile.
    current = app.agent_profile_name_var.get().strip()
    if not current or current in app._agent_presets:
        app.agent_profile_name_var.set(preset.name)
    app.agent_key_var.set("")


def _set_model_choices(app, models, *, keep: str = "") -> None:
    choices = list(dict.fromkeys([*models, *([keep] if keep else [])]))
    app.agent_model_combo.configure(values=choices)
    if keep:
        app.agent_model_var.set(keep)
    elif app.agent_model_var.get() not in choices:
        app.agent_model_var.set(choices[0] if choices else "")


def fetch_model_list(app) -> None:
    """Ask the provider for its models (GET /models) using the typed or stored key."""
    if str(app.agent_fetch_models_button["state"]) == "disabled":
        return
    base_url = app.agent_base_url_var.get().strip()
    auth_style = app.agent_auth_var.get()
    key = app.agent_key_var.get().strip()
    if not key:
        name = app.agent_profile_name_var.get().strip()
        try:
            same_endpoint = app._agent_profiles.get(name).base_url == base_url
        except KeyError:
            same_endpoint = False
        key = (app._agent_profiles.api_key(name) or "") if same_endpoint else ""
    if not key:
        messagebox.showinfo("需要 API Key", "请先填写这家厂商的 API Key，再获取模型列表。")
        return
    mismatch = key_mismatch_hint(base_url, key)
    if mismatch:
        messagebox.showinfo("Key 与接口不匹配", mismatch)
        return
    app.agent_fetch_models_button.state(["disabled"])
    app._set_status("正在获取模型列表…")
    captured_base_url = base_url

    def worker() -> None:
        try:
            models = fetch_models(base_url, auth_style, key)
        except ValueError as exc:
            app._ui_callbacks.submit(lambda error=exc: _models_failed(app, error))
            return
        app._ui_callbacks.submit(lambda: _models_loaded(app, models, captured_base_url))

    threading.Thread(target=worker, daemon=True).start()


def _models_loaded(app, models, base_url: str | None = None) -> None:
    if base_url is not None and app.agent_base_url_var.get().strip() != base_url:
        return
    app.agent_fetch_models_button.state(["!disabled"])
    _set_model_choices(app, models)
    app._set_status(f"已获取 {len(models)} 个模型，请在下拉框中选择")


def _models_failed(app, error: Exception) -> None:
    app.agent_fetch_models_button.state(["!disabled"])
    messagebox.showinfo("获取模型列表失败", str(error))


def refresh_profiles(app) -> None:
    """Refresh every place that lists model profiles (Settings, Agents, translation)."""
    names = [profile.name for profile in app.model_profiles.list()]
    if hasattr(app, "agent_profile_combo"):
        app.agent_profile_combo.configure(values=names)
        if app.agent_profile_var.get() not in names:
            app.agent_profile_var.set(names[0] if names else "")
        if app.agent_profile_var.get():
            load_profile(app)
        else:
            _update_key_status(app, None)
    if hasattr(app, "agent_run_profile_combo"):
        app.agent_run_profile_combo.configure(values=names)
        if app.agent_run_profile_var.get() not in names:
            app.agent_run_profile_var.set(names[0] if names else "")
        _update_send_notice(app)
    if hasattr(app, "translation_profile_combo"):
        app.translation_profile_combo.configure(values=names)
    if hasattr(app, "intelligence_ai_profile_combo"):
        app.intelligence_ai_profile_combo.configure(values=names)
        if app.intelligence_ai_profile_var.get() not in names:
            app.intelligence_ai_profile_var.set(names[0] if names else "")
    if hasattr(app, "_reload_translation_provider"):
        app._reload_translation_provider()  # a translation profile may have changed


def load_profile(app) -> None:
    try:
        profile = app._agent_profiles.get(app.agent_profile_var.get())
    except KeyError:
        return
    preset_names = {p.preset_id: p.name for p in app._agent_presets.values()}
    app.agent_preset_var.set(preset_names.get(profile.preset_id, ""))
    app.agent_profile_name_var.set(profile.name)
    app.agent_base_url_var.set(profile.base_url)
    app.agent_auth_var.set(profile.auth_style)
    presets = app._agent_presets.values()
    suggested = next(
        (p.suggested_models for p in presets if p.preset_id == profile.preset_id), ()
    )
    _set_model_choices(app, suggested, keep=profile.model)
    app.agent_key_var.set("")
    _update_key_status(app, profile.name)


def save_profile(app) -> None:
    preset = app._agent_presets.get(app.agent_preset_var.get())
    try:
        profile = ModelProfile(
            name=app.agent_profile_name_var.get().strip(),
            preset_id=preset.preset_id if preset else "custom",
            base_url=app.agent_base_url_var.get().strip(),
            auth_style=app.agent_auth_var.get(),
            model=app.agent_model_var.get().strip(),
        )
        new_key = app.agent_key_var.get().strip()
        mismatch = key_mismatch_hint(profile.base_url, new_key)
        if mismatch:
            raise ValueError(mismatch)
        try:
            existing = app._agent_profiles.get(profile.name)
        except KeyError:
            existing = None
        if existing is not None and existing.base_url != profile.base_url and not new_key:
            # Never send one provider's stored key to a different endpoint.
            raise ValueError(
                f"配置“{profile.name}”的接口地址变了，请填写这家厂商的 API Key，"
                "或改用新的配置名称"
            )
        app._agent_profiles.save(profile, new_key)
    except (ValueError, OSError) as exc:
        messagebox.showinfo("配置未保存", str(exc))
        return
    app.agent_key_var.set("")
    app.agent_profile_var.set(profile.name)
    refresh_profiles(app)
    app._set_status(f"模型配置“{profile.name}”已保存")


def delete_profile(app) -> None:
    name = app.agent_profile_var.get()
    if not name or not messagebox.askyesno("删除配置", f"删除模型配置“{name}”及其 API Key？"):
        return
    app._agent_profiles.delete(name)
    app.agent_profile_var.set("")
    refresh_profiles(app)


def _update_key_status(app, name: str | None) -> None:
    if not name:
        app.agent_key_status_var.set("尚无配置：选择厂商预设并填写 API Key 后保存")
        return
    has_key = bool(app._agent_profiles.api_key(name))
    where = "Windows 凭据管理器" if app._agent_profiles.secrets.persistent else "本次运行内存"
    app.agent_key_status_var.set(
        f"API Key 已保存在{where}" if has_key else "该配置尚未保存 API Key"
    )


# -- run -----------------------------------------------------------------------


def _build_run_section(app, page) -> None:
    box = ttk.LabelFrame(page, text="1. 选择智能体和模型并提问", padding=10)
    box.pack(fill="x", pady=(10, 0))
    app.agent_choice_var = tk.StringVar()
    app.agent_description_var = tk.StringVar()
    app.agent_definition_errors_var = tk.StringVar()

    ttk.Label(box, text="智能体").pack(anchor="w")
    app._agent_card_grid = ttk.Frame(box, style="Surface.TFrame")
    app._agent_card_grid.pack(fill="x", pady=(4, 8))
    app._agent_cards: dict[str, Card] = {}

    row = ttk.Frame(box)
    row.pack(fill="x")
    ttk.Button(row, text="重新加载定义", command=lambda: reload_agents(app)).pack(side="left")
    ttk.Label(row, text="模型").pack(side="left", padx=(24, 0))
    app.agent_run_profile_var = tk.StringVar()
    app.agent_run_profile_combo = ttk.Combobox(
        row, textvariable=app.agent_run_profile_var, state="readonly", width=30
    )
    app.agent_run_profile_combo.pack(side="left", padx=6)
    ttk.Label(row, text="在“设置 → AI 模型配置”中新增或修改", style="Subtle.TLabel").pack(
        side="left"
    )
    ttk.Label(box, textvariable=app.agent_description_var, style="Subtle.TLabel").pack(
        anchor="w", pady=(4, 0)
    )
    ttk.Label(
        box,
        textvariable=app.agent_definition_errors_var,
        foreground="#B42318",
        wraplength=1100,
        justify="left",
    ).pack(anchor="w")
    app.agent_question = tk.Text(box, height=4, wrap="word")
    app.agent_question.pack(fill="x", pady=(6, 0))
    buttons = ttk.Frame(box)
    buttons.pack(fill="x", pady=(6, 0))
    app.agent_run_button = ttk.Button(buttons, text="运行", command=lambda: run_agent(app))
    app.agent_run_button.pack(side="left")
    app.agent_cancel_button = ttk.Button(
        buttons, text="取消", command=lambda: cancel_agent(app), state="disabled"
    )
    app.agent_cancel_button.pack(side="left", padx=8)
    ttk.Button(buttons, text="在浏览器中查看结果", command=lambda: open_last_html(app)).pack(
        side="left"
    )
    ttk.Button(buttons, text="打开运行日志", command=lambda: open_last_log(app)).pack(
        side="left", padx=8
    )
    app.agent_send_notice_var = tk.StringVar()
    ttk.Label(
        box, textvariable=app.agent_send_notice_var, style="Subtle.TLabel", wraplength=1100
    ).pack(anchor="w", pady=(4, 0))
    app.agent_run_profile_var.trace_add("write", lambda *_: _update_send_notice(app))


def _update_send_notice(app) -> None:
    """Standing notice of what a run sends where (replaces the per-run consent popup)."""
    try:
        profile = app.model_profiles.get(app.agent_run_profile_var.get())
    except KeyError:
        app.agent_send_notice_var.set("尚无模型配置：请先在 设置 → AI 模型配置 中添加")
        return
    app.agent_send_notice_var.set(
        f"运行时会把问题和工具查到的公开专利资料发送到 {profile.host}（{profile.model}）；"
        "笔记、项目、标签、监控规则不会发送。"
    )


def reload_agents(app) -> None:
    definitions, errors = load_definitions((app._agent_user_dir,))
    app._agent_definitions: dict[str, AgentDefinition] = {d.name: d for d in definitions}
    _rebuild_agent_cards(app)
    if app.agent_choice_var.get() not in app._agent_definitions:
        app.agent_choice_var.set(next(iter(app._agent_definitions), ""))
    app.agent_definition_errors_var.set(
        "以下定义文件未加载：\n" + "\n".join(errors) if errors else ""
    )
    _describe_agent(app)


def _rebuild_agent_cards(app) -> None:
    for widget in app._agent_card_grid.winfo_children():
        widget.destroy()
    app._agent_cards = {}
    for index, definition in enumerate(app._agent_definitions.values()):
        row, col = divmod(index, 3)
        card = Card(
            app._agent_card_grid,
            icon="🤖",
            title=definition.name,
            description=definition.description,
            on_click=lambda name=definition.name: select_agent(app, name),
        )
        card.frame.grid(row=row, column=col, sticky="nsew", padx=4, pady=4)
        app._agent_card_grid.columnconfigure(col, weight=1)
        app._agent_cards[definition.name] = card
    _highlight_agent_cards(app)


def select_agent(app, name: str) -> None:
    app.agent_choice_var.set(name)
    _highlight_agent_cards(app)
    _describe_agent(app)


def _highlight_agent_cards(app) -> None:
    current = app.agent_choice_var.get()
    for name, card in app._agent_cards.items():
        card.set_active(name == current)


def _describe_agent(app) -> None:
    definition = app._agent_definitions.get(app.agent_choice_var.get())
    if definition is None:
        app.agent_description_var.set("")
        return
    checkpoints = "、".join(definition.checkpoints) or "无"
    app.agent_description_var.set(
        f"{definition.description}｜可用工具 {len(definition.tools)} 个｜"
        f"最多 {definition.max_steps} 步｜确认节点：{checkpoints}"
    )


def run_agent(app) -> None:
    if str(app.agent_run_button["state"]) == "disabled":
        return
    definition = app._agent_definitions.get(app.agent_choice_var.get())
    question = app.agent_question.get("1.0", "end").strip()
    if definition is None or not question:
        messagebox.showinfo("尚未准备好", "请选择智能体并填写问题。")
        return
    try:
        profile = app.model_profiles.get(app.agent_run_profile_var.get())
    except KeyError:
        messagebox.showinfo("尚未准备好", "请先在 设置 → AI 模型配置 中保存一个模型配置。")
        return
    api_key = app._agent_profiles.api_key(profile.name)
    if not api_key:
        messagebox.showinfo("尚未准备好", f"模型配置“{profile.name}”还没有 API Key。")
        return
    try:
        tools = open_read_only(app.runtime.library_store.path)
    except FileNotFoundError as exc:
        messagebox.showerror("无法打开本地库", str(exc))
        return

    cancel = threading.Event()
    app._agent_cancel = cancel
    app._agent_last_html = None
    runner = AgentRunner(
        definition,
        profile,
        api_key,
        tools,
        log_dir=app._agent_log_dir,
        on_checkpoint=lambda kind, payload: _checkpoint_from_worker(app, kind, payload),
        on_progress=lambda text: app._ui_callbacks.submit(lambda t=text: app._set_status(t)),
        cancel_event=cancel,
    )
    app.agent_run_button.state(["disabled"])
    app.agent_cancel_button.state(["!disabled"])
    _set_output(app, f"{definition.name} 运行中…")
    app._set_status("智能体运行中…")

    def worker() -> None:
        try:
            result = runner.run(question)
        except Exception as exc:
            app._ui_callbacks.submit(lambda error=exc: _show_error(app, error))
            return
        finally:
            tools.store.close()
        app._ui_callbacks.submit(lambda: show_result(app, result))

    threading.Thread(target=worker, daemon=True).start()


def cancel_agent(app) -> None:
    if app._agent_cancel is not None:
        app._agent_cancel.set()
    pending = app._agent_pending_checkpoint
    if pending is not None:
        holder, event = pending
        holder["decision"] = CheckpointDecision(False)
        event.set()
    dialog = getattr(app, "_agent_checkpoint_dialog", None)
    if dialog is not None and dialog.winfo_exists():
        dialog.destroy()
    app._set_status("正在取消…")


def _checkpoint_from_worker(app, kind: str, payload: str) -> CheckpointDecision:
    """Runs on the worker thread: ask the Tk thread and wait for the answer."""
    holder: dict = {"decision": CheckpointDecision(False)}
    event = threading.Event()
    app._agent_pending_checkpoint = (holder, event)
    app._ui_callbacks.submit(lambda: _checkpoint_dialog(app, kind, payload, holder, event))
    event.wait()
    app._agent_pending_checkpoint = None
    return holder["decision"]


def _checkpoint_dialog(app, kind, payload, holder, event) -> None:
    if event.is_set():
        return
    title, prompt = _CHECKPOINT_TITLES.get(kind, ("确认", "请确认："))
    dialog = tk.Toplevel(app)
    dialog.title(title)
    dialog.transient(app)
    ttk.Label(dialog, text=prompt, padding=(12, 10, 12, 4)).pack(anchor="w")
    text = tk.Text(dialog, width=90, height=18, wrap="word")
    text.insert("1.0", payload)
    text.pack(fill="both", expand=True, padx=12)

    def finish(approved: bool) -> None:
        if not event.is_set():
            content = text.get("1.0", "end").rstrip("\n")
            holder["decision"] = CheckpointDecision(approved, content if approved else "")
            event.set()
        dialog.destroy()

    buttons = ttk.Frame(dialog, padding=12)
    buttons.pack(fill="x")
    ttk.Button(buttons, text="确认", command=lambda: finish(True)).pack(side="right")
    ttk.Button(buttons, text="取消运行", command=lambda: finish(False)).pack(
        side="right", padx=8
    )
    dialog.protocol("WM_DELETE_WINDOW", lambda: finish(False))
    app._agent_checkpoint_dialog = dialog


# -- result --------------------------------------------------------------------


def _build_result_section(app, page) -> None:
    box = ttk.LabelFrame(page, text="2. 结果（⚠ 行需要复核）", padding=10)
    box.pack(fill="both", expand=True, pady=(10, 0))
    app.agent_banner_var = tk.StringVar()
    ttk.Label(box, textvariable=app.agent_banner_var).pack(anchor="w")
    frame = ttk.Frame(box)
    frame.pack(fill="both", expand=True, pady=(4, 0))
    app.agent_output = tk.Text(
        frame, height=20, wrap="word", padx=14, pady=10, relief="flat",
        font=("Microsoft YaHei UI", 10), spacing1=2, spacing3=2,
    )
    scroll = ttk.Scrollbar(frame, orient="vertical", command=app.agent_output.yview)
    app.agent_output.configure(yscrollcommand=scroll.set)
    scroll.pack(side="right", fill="y")
    app.agent_output.pack(side="left", fill="both", expand=True)
    tags = {
        "h2": {"font": ("Microsoft YaHei UI", 12, "bold"), "foreground": "#1261D6",
               "spacing1": 12, "spacing3": 4},
        "h3": {"font": ("Microsoft YaHei UI", 10, "bold"), "spacing1": 8},
        "bullet": {"lmargin1": 8, "lmargin2": 24},
        "rowtitle": {"font": ("Microsoft YaHei UI", 10, "bold"), "lmargin1": 8,
                     "spacing1": 6},
        "field": {"lmargin1": 28, "lmargin2": 28, "foreground": "#3E4C59"},
        "cite": {"foreground": "#1261D6", "font": ("Consolas", 9)},
        "flagged": {"background": "#FDECEC"},
        "note": {"foreground": "#B42318", "font": ("Microsoft YaHei UI", 9)},
    }
    for name, options in tags.items():
        app.agent_output.tag_configure(name, **options)
    app._agent_last_html = None
    app.agent_output.configure(state="disabled")


def _set_output(app, text: str) -> None:
    app.agent_output.configure(state="normal")
    app.agent_output.delete("1.0", "end")
    app.agent_output.insert("1.0", text)
    app.agent_output.configure(state="disabled")


def show_result(app, result: AgentResult) -> None:
    _reset_buttons(app)
    app._agent_last_log = result.log_path
    flagged = result.check.flagged_count if result.check else 0
    model = result.log.get("model", {})
    banner = (
        f"状态：{_STATUS_TEXT.get(result.status, result.status)}｜"
        f"{model.get('profile', '')} · {model.get('model', '')}｜步数 {result.steps}｜"
        f"本次工具返回公开号 {len(result.receipts)} 个｜需复核的行 {flagged}"
    )
    app.agent_banner_var.set(banner)
    app.agent_output.configure(state="normal")
    app.agent_output.delete("1.0", "end")
    if result.error:
        app.agent_output.insert("end", result.error + "\n", "note")
    elif result.check is None:
        app.agent_output.insert("end", result.final_text or "（没有生成回答）")
    else:
        _render_blocks(app.agent_output, result.check)
        app._agent_last_html = _save_html(app, result, banner)
    app.agent_output.configure(state="disabled")
    app._set_status("智能体运行结束")


def _insert_inline(widget, text: str, tags: tuple[str, ...]) -> None:
    for part, is_cite in text_parts(text):
        widget.insert("end", part, (*tags, "cite") if is_cite else tags)


def _insert_flag(widget, line) -> None:
    if line is not None and line.flagged:
        widget.insert("end", f"\n    ⚠ {line.detail}", ("note",))


def _render_blocks(widget, check) -> None:
    for block in blocks(check):
        flagged = ("flagged",) if block.line is not None and block.line.flagged else ()
        if block.kind == "heading":
            widget.insert("end", block.text + "\n", ("h2" if block.level <= 2 else "h3",))
        elif block.kind == "bullet":
            _insert_inline(widget, "•  " + block.text, ("bullet", *flagged))
            _insert_flag(widget, block.line)
            widget.insert("end", "\n")
        elif block.kind == "paragraph":
            _insert_inline(widget, block.text, flagged)
            _insert_flag(widget, block.line)
            widget.insert("end", "\n")
        else:
            # Tables become one card per row so long cells wrap instead of being cut off.
            for cells, line in block.rows:
                row_flag = ("flagged",) if line.flagged else ()
                title = cells[0] if cells else ""
                _insert_inline(widget, "▸ " + title + "\n", ("rowtitle", *row_flag))
                for name, value in zip(block.header[1:], cells[1:], strict=False):
                    _insert_inline(widget, f"{name}：{value}\n", ("field", *row_flag))
                if line.flagged:
                    widget.insert("end", f"    ⚠ {line.detail}\n", ("note",))


def _save_html(app, result: AgentResult, banner: str):
    model = result.log.get("model", {})
    html = render_html(
        result.check,
        title=app.agent_choice_var.get() or "智能体结果",
        question=result.log.get("question", ""),
        meta=f"模型：{model.get('profile', '')} · {model.get('model', '')}｜"
        f"时间：{result.log.get('finished_at', '')}",
        banner=banner,
    )
    if result.log_path is not None:
        path = result.log_path.with_suffix(".html")
    else:
        app._agent_log_dir.mkdir(parents=True, exist_ok=True)
        path = app._agent_log_dir / "latest.html"
    path.write_text(html, encoding="utf-8")
    return path


def open_last_html(app) -> None:
    if app._agent_last_html and app._agent_last_html.exists():
        open_local_path(app._agent_last_html)
    else:
        messagebox.showinfo("暂无结果", "还没有可查看的结果。")


def _show_error(app, error: Exception) -> None:
    _reset_buttons(app)
    messagebox.showerror("智能体运行失败", str(error))


def _reset_buttons(app) -> None:
    app._agent_cancel = None
    app.agent_run_button.state(["!disabled"])
    app.agent_cancel_button.state(["disabled"])


def open_last_log(app) -> None:
    if app._agent_last_log and app._agent_last_log.exists():
        open_local_path(app._agent_last_log)
    elif app._agent_log_dir.exists():
        open_local_path(app._agent_log_dir)
    else:
        messagebox.showinfo("暂无日志", "还没有运行记录。")
