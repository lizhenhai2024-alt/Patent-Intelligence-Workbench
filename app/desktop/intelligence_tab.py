"""Desktop entry point for local engineering-intelligence workflows."""

from __future__ import annotations

import threading
import tkinter as tk
from datetime import date
from tkinter import filedialog, messagebox, ttk

from app.desktop.opening import open_local_path
from app.intelligence.ai_interpreter import (
    AIInterpretationSettings,
    OpenAICompatibleInterpreter,
)
from app.intelligence.ai_packet import build_ai_prompt
from app.intelligence.analysis import AnalysisReport, AnalysisScope, AnalysisService
from app.intelligence.guidance import (
    WorkflowGuide,
    validate_task_inputs,
    workflow_guide,
    workflow_guides,
)
from app.intelligence.readiness import assess_library_readiness
from app.intelligence.report import save_html
from app.intelligence.search_plan import plan_search
from app.intelligence.watch_review import ReviewItem, WatchReviewStore

_WORKFLOWS = tuple(guide.name for guide in workflow_guides())
_STATUS_LABELS = {"pending": "待复核", "important": "重要", "ignored": "忽略"}
_LABEL_STATUSES = {value: key for key, value in _STATUS_LABELS.items()}


def _split(value: str) -> tuple[str, ...]:
    return tuple(part.strip() for part in value.replace("，", ",").split(",") if part.strip())


def _year(value: str, *, end: bool) -> date | None:
    value = value.strip()
    if not value:
        return None
    year = int(value)
    if year < 1782 or year > date.today().year + 1:
        raise ValueError("年份超出支持范围")
    return date(year, 12, 31) if end else date(year, 1, 1)


def build_intelligence_tab(app) -> None:
    page = app.intelligence_tab
    ttk.Label(page, text="工程专利情报任务", style="PageTitle.TLabel").pack(anchor="w")
    ttk.Label(
        page,
        text="从一个明确工程任务开始；每个结论均保留本地公开件来源和适用边界",
        style="Subtle.TLabel",
    ).pack(anchor="w", pady=(2, 12))

    app.intelligence_workflow_var = tk.StringVar(value=_WORKFLOWS[0])
    app.intelligence_topic_var = tk.StringVar()
    app.intelligence_companies_var = tk.StringVar()
    app.intelligence_routes_var = tk.StringVar()
    app.intelligence_countries_var = tk.StringVar()
    app.intelligence_start_var = tk.StringVar()
    app.intelligence_end_var = tk.StringVar()
    app.intelligence_query_var = tk.StringVar()
    app._intelligence_report: AnalysisReport | None = None
    app._intelligence_review_items: dict[str, ReviewItem] = {}
    app._intelligence_next_action = "search"

    chooser = ttk.LabelFrame(page, text="1. 选择任务", padding=10)
    chooser.pack(fill="x")
    app._intelligence_workflow_buttons: dict[str, ttk.Button] = {}
    for index, guide in enumerate(workflow_guides()):
        row, col = divmod(index, 3)
        button = ttk.Button(
            chooser,
            text=f"{guide.name}\n{guide.purpose}",
            command=lambda name=guide.name: select_workflow(app, name),
        )
        button.grid(row=row, column=col, sticky="nsew", padx=4, pady=4)
        app._intelligence_workflow_buttons[guide.name] = button
        chooser.columnconfigure(col, weight=1)

    context = ttk.LabelFrame(page, text="2. 任务说明", padding=10)
    context.pack(fill="x", pady=(10, 0))
    app.intelligence_task_context_var = tk.StringVar()
    ttk.Label(
        context,
        textvariable=app.intelligence_task_context_var,
        justify="left",
        wraplength=1100,
        style="Subtle.TLabel",
    ).pack(anchor="w")

    readiness = ttk.LabelFrame(page, text="数据就绪度", padding=10)
    readiness.pack(fill="x", pady=(10, 0))
    app.intelligence_readiness_var = tk.StringVar()
    ttk.Label(
        readiness,
        textvariable=app.intelligence_readiness_var,
        justify="left",
        wraplength=970,
        style="Subtle.TLabel",
    ).pack(side="left", fill="x", expand=True)
    ttk.Button(readiness, text="继续处理数据", command=lambda: continue_task(app)).pack(
        side="left", padx=(10, 0)
    )

    form = ttk.LabelFrame(page, text="3. 填写当前任务需要的信息", padding=12)
    form.pack(fill="x", pady=(10, 0))
    app._intelligence_field_frames: dict[str, ttk.Frame] = {}

    fields = (
        ("topic", "技术主题 / 工程问题", app.intelligence_topic_var),
        ("companies", "公司组（逗号分隔）", app.intelligence_companies_var),
        ("routes", "技术路线（节点 ID 或精确名称，逗号分隔）", app.intelligence_routes_var),
        ("countries", "国家/局（如 CN, JP, US）", app.intelligence_countries_var),
        ("start", "起始年份", app.intelligence_start_var),
        ("end", "结束年份", app.intelligence_end_var),
    )
    for index, (key, label, variable) in enumerate(fields):
        row, col = divmod(index, 2)
        cell = ttk.Frame(form)
        cell.grid(row=row, column=col, sticky="ew", padx=(0, 16), pady=5)
        ttk.Label(cell, text=label).pack(anchor="w")
        ttk.Entry(cell, textvariable=variable).pack(fill="x")
        app._intelligence_field_frames[key] = cell
    form.columnconfigure(0, weight=1)
    form.columnconfigure(1, weight=1)

    buttons = ttk.Frame(page)
    buttons.pack(fill="x", pady=(10, 6))
    ttk.Button(buttons, text="运行任务", command=lambda: run_task(app)).pack(side="left")
    ttk.Button(buttons, text="保存离线 HTML", command=lambda: save_report(app)).pack(
        side="left", padx=8
    )
    ttk.Button(buttons, text="复制 AI 解读提示词", command=lambda: copy_ai_prompt(app)).pack(
        side="left", padx=8
    )
    ttk.Button(buttons, text="查看证据", command=lambda: continue_task(app, "evidence")).pack(
        side="left"
    )

    search = ttk.LabelFrame(page, text="检索词预览（可编辑；确认后转到原有检索页）", padding=10)
    search.pack(fill="x", pady=(0, 10))
    ttk.Entry(search, textvariable=app.intelligence_query_var).pack(
        side="left", fill="x", expand=True
    )
    ttk.Button(search, text="带到检索页", command=lambda: send_to_search(app)).pack(
        side="left", padx=(8, 0)
    )

    result = ttk.LabelFrame(page, text="4. 结果与下一步", padding=6)
    result.pack(fill="both", expand=True, pady=(0, 10))
    app.intelligence_preview = tk.Text(result, height=11, wrap="word", state="disabled")
    app.intelligence_preview.pack(fill="both", expand=True)

    ai = ttk.LabelFrame(page, text="可选 AI 解读（仅在你确认后发送当前报告证据包）", padding=10)
    ai.pack(fill="x", pady=(0, 10))
    app.intelligence_ai_endpoint_var = tk.StringVar()
    app.intelligence_ai_model_var = tk.StringVar()
    app.intelligence_ai_key_var = tk.StringVar()
    app.intelligence_ai_consent_var = tk.BooleanVar(value=False)
    for index, (label, variable, secret) in enumerate(
        (
            ("Chat Completions Endpoint", app.intelligence_ai_endpoint_var, False),
            ("模型", app.intelligence_ai_model_var, False),
            ("API Key（仅本次窗口使用）", app.intelligence_ai_key_var, True),
        )
    ):
        cell = ttk.Frame(ai)
        cell.grid(row=0, column=index, sticky="ew", padx=(0, 10))
        ttk.Label(cell, text=label).pack(anchor="w")
        ttk.Entry(cell, textvariable=variable, show="•" if secret else "").pack(fill="x")
        ai.columnconfigure(index, weight=1)
    ttk.Checkbutton(
        ai,
        text="我确认发送当前报告中的证据包给上述 AI 服务",
        variable=app.intelligence_ai_consent_var,
    ).grid(row=1, column=0, columnspan=2, sticky="w", pady=(8, 0))
    ttk.Button(ai, text="请求 AI 解读", command=lambda: run_ai_interpretation(app)).grid(
        row=1, column=2, sticky="e", pady=(8, 0)
    )

    review = ttk.LabelFrame(page, text="监控事件复核", padding=10)
    review.pack(fill="both", expand=True, pady=(10, 0))
    app.intelligence_review_tree = ttk.Treeview(
        review,
        columns=("date", "rule", "type", "number", "status"),
        show="headings",
        height=6,
    )
    for key, label, width in (
        ("date", "发现时间", 170),
        ("rule", "监控规则", 160),
        ("type", "事件类型", 220),
        ("number", "公开号", 180),
        ("status", "复核状态", 90),
    ):
        app.intelligence_review_tree.heading(key, text=label)
        app.intelligence_review_tree.column(key, width=width)
    app.intelligence_review_tree.pack(fill="both", expand=True)
    app.intelligence_review_tree.bind(
        "<<TreeviewSelect>>", lambda _event: load_review_selection(app)
    )
    review_actions = ttk.Frame(review)
    review_actions.pack(fill="x", pady=(8, 0))
    app.intelligence_review_status_var = tk.StringVar(value="待复核")
    ttk.Combobox(
        review_actions,
        textvariable=app.intelligence_review_status_var,
        values=tuple(_LABEL_STATUSES),
        state="readonly",
        width=10,
    ).pack(side="left")
    app.intelligence_review_note_var = tk.StringVar()
    ttk.Entry(review_actions, textvariable=app.intelligence_review_note_var).pack(
        side="left", fill="x", expand=True, padx=8
    )
    ttk.Button(review_actions, text="保存复核", command=lambda: save_review(app)).pack(side="left")
    ttk.Button(review_actions, text="刷新", command=lambda: refresh_reviews(app)).pack(
        side="left", padx=(8, 0)
    )
    app.intelligence_workflow_var.trace_add("write", lambda *_: refresh_task_workspace(app))
    refresh_task_workspace(app)
    refresh_reviews(app)


def _preview(app, text: str) -> None:
    widget = app.intelligence_preview
    widget.configure(state="normal")
    widget.delete("1.0", "end")
    widget.insert("1.0", text)
    widget.configure(state="disabled")


def select_workflow(app, name: str) -> None:
    app.intelligence_workflow_var.set(name)


def _selected_guide(app) -> WorkflowGuide:
    return workflow_guide(app.intelligence_workflow_var.get())


def refresh_task_workspace(app) -> None:
    """Show task-specific instructions and avoid a one-size-fits-all form."""
    guide = _selected_guide(app)
    app.intelligence_task_context_var.set(
        "\n".join(
            (
                f"用途：{guide.purpose}",
                f"需要：{guide.inputs}",
                f"输出：{guide.output}",
                f"边界：{guide.limit}",
                f"示例：{guide.example}",
            )
        )
    )
    for name, button in app._intelligence_workflow_buttons.items():
        button.configure(style="Accent.TButton" if name == guide.name else "TButton")
    visible = {
        "topic": guide.workflow_id != "watch-brief",
        "companies": guide.needs_companies > 0,
        "routes": guide.needs_routes > 0,
        "countries": guide.uses_library,
        "start": guide.uses_library,
        "end": guide.uses_library,
    }
    for key, frame in app._intelligence_field_frames.items():
        if visible[key]:
            frame.grid()
        else:
            frame.grid_remove()
    refresh_readiness(app)


def refresh_readiness(app) -> None:
    guide = _selected_guide(app)
    readiness = assess_library_readiness(app.runtime.library_store, guide)
    app._intelligence_readiness = readiness
    app.intelligence_readiness_var.set(f"{readiness.summary}\n{readiness.detail}")


def continue_task(app, action: str | None = None) -> None:
    choice = action or getattr(app, "_intelligence_next_action", None)
    if choice is None:
        choice = getattr(app, "_intelligence_readiness", None)
        choice = choice.next_action if choice else "search"
    if choice == "search":
        app._show_page("search")
        app._set_status("请先检索并保存与当前任务相关的专利。")
    elif choice == "library":
        app._show_page("library")
        app._set_status("请同步本地专利库，并复核公司组、技术节点和 Family 元数据。")
    elif choice == "evidence":
        app._show_page("evidence")
        app._set_status("请在 Evidence 中查看或补充报告涉及的原始证据。")
    else:
        run_task(app)


def run_task(app) -> None:
    guide = _selected_guide(app)
    topic = app.intelligence_topic_var.get().strip()
    companies = _split(app.intelligence_companies_var.get())
    routes = _split(app.intelligence_routes_var.get())
    try:
        validate_task_inputs(guide, topic=topic, companies=companies, routes=routes)
        readiness = assess_library_readiness(app.runtime.library_store, guide)
        app._intelligence_readiness = readiness
        if not readiness.can_run:
            app._intelligence_next_action = readiness.next_action
            _preview(
                app,
                "\n".join(
                    (
                        readiness.summary,
                        readiness.detail,
                        "点击“继续处理数据”进入下一步；补充数据后再运行分析。",
                    )
                ),
            )
            app._set_status("当前任务需要先补充本地数据。")
            return
        scope = AnalysisScope(
            topic="" if guide.workflow_id in {"problem-search", "watch-brief"} else topic,
            jurisdictions=_split(app.intelligence_countries_var.get()),
            from_date=_year(app.intelligence_start_var.get(), end=False),
            to_date=_year(app.intelligence_end_var.get(), end=True),
        )
        if guide.workflow_id == "problem-search":
            plan = plan_search(topic)
            app.intelligence_query_var.set(plan.editable_query)
            lines = [f"问题：{plan.problem}", "建议词组（请编辑后自行运行检索）："]
            lines += [
                f"{group.topic_name} [{group.source}]：{' / '.join(group.terms)}"
                for group in plan.groups
            ]
            if plan.unmatched:
                lines.append("词典未识别该问题；保留原问题供人工编辑。")
            lines.append("\n下一步：编辑检索词后点击“带到检索页”，再由你确认范围并执行检索。")
            app._intelligence_next_action = "search"
            _preview(app, "\n".join(lines))
            return
    except (ValueError, KeyError) as exc:
        messagebox.showerror("任务条件错误", str(exc))
        return

    app._intelligence_report = None
    _preview(app, "正在分析当前 LocalLibrary…")
    app._set_status("工程情报任务运行中…")

    def worker() -> None:
        try:
            if guide.workflow_id == "watch-brief":
                review = WatchReviewStore(app.runtime.paths.library_db)
                try:
                    report = review.brief()
                finally:
                    review.close()
            else:
                service = AnalysisService(app.runtime.library_store)
                if guide.workflow_id == "landscape":
                    report = service.landscape(scope)
                elif guide.workflow_id == "company-profile":
                    report = service.company_profile(scope, companies[0])
                elif guide.workflow_id == "competitive-landscape":
                    report = service.competitive_landscape(scope, companies)
                else:
                    report = service.route_comparison(scope, routes)
        except Exception as exc:
            app._ui_callbacks.submit(lambda error=exc: messagebox.showerror("任务失败", str(error)))
            return
        app._ui_callbacks.submit(lambda result=report: _show_report(app, result))

    threading.Thread(target=worker, daemon=True).start()


def _show_report(app, report: AnalysisReport) -> None:
    app._intelligence_report = report
    lines = [report.title, report.scope, ""]
    lines.extend(f"{metric.label}：{metric.value}（{metric.formula}）" for metric in report.metrics)
    lines.extend(
        (
            "",
            "下一步：保存 HTML 可逐项展开来源公开件与统计口径；也可进入 Evidence 补充原始材料。",
            "AI 解读仅在你填写服务并明确确认发送后才会调用外部服务。",
        )
    )
    _preview(app, "\n".join(lines))
    app._set_status(f"已生成：{report.title}")
    app._intelligence_next_action = "evidence"
    if report.workflow == "watch-brief":
        refresh_reviews(app)


def save_report(app) -> None:
    report = app._intelligence_report
    if report is None:
        messagebox.showinfo("尚无报告", "请先运行一个分析任务。")
        return
    path = filedialog.asksaveasfilename(
        title="保存工程情报报告",
        initialdir=app.runtime.paths.exports,
        defaultextension=".html",
        filetypes=[("HTML 报告", "*.html")],
    )
    if not path:
        return
    try:
        saved = save_html(report, path)
        open_local_path(saved)
        app._set_status(f"报告已保存：{saved}")
    except Exception as exc:
        messagebox.showerror("保存失败", str(exc))


def copy_ai_prompt(app) -> None:
    report = app._intelligence_report
    if report is None:
        messagebox.showinfo("尚无报告", "请先运行一个分析任务。")
        return
    prompt = build_ai_prompt(report)
    app.clipboard_clear()
    app.clipboard_append(prompt)
    app.update_idletasks()
    app._set_status("证据提示词已复制；只有手动粘贴时才会发给所选 AI。")


def run_ai_interpretation(app) -> None:
    report = app._intelligence_report
    if report is None:
        messagebox.showinfo("尚无报告", "请先生成并审阅一个本地报告。")
        return
    try:
        settings = AIInterpretationSettings(
            endpoint=app.intelligence_ai_endpoint_var.get().strip(),
            model=app.intelligence_ai_model_var.get().strip(),
            api_key=app.intelligence_ai_key_var.get(),
            consent=app.intelligence_ai_consent_var.get(),
        )
    except ValueError as exc:
        messagebox.showinfo("AI 解读尚未准备好", str(exc))
        return
    _preview(app, "正在向你指定的 AI 服务发送当前报告证据包…")
    app._set_status("AI 解读运行中…")

    def worker() -> None:
        try:
            text = OpenAICompatibleInterpreter(settings).interpret(report)
        except Exception as exc:
            app._ui_callbacks.submit(
                lambda error=exc: messagebox.showerror("AI 解读失败", str(error))
            )
            return
        app._ui_callbacks.submit(lambda result=text: _show_ai_interpretation(app, result))

    threading.Thread(target=worker, daemon=True).start()


def _show_ai_interpretation(app, interpretation: str) -> None:
    _preview(
        app,
        "\n".join(
            (
                "AI 解读（需结合原始公开件复核）",
                "以下内容由你指定的外部 AI 服务返回，不构成侵权、FTO、有效性或市场结论。",
                "",
                interpretation,
            )
        ),
    )
    app._set_status("AI 解读已返回；请依据报告中的公开件来源复核。")


def send_to_search(app) -> None:
    query = app.intelligence_query_var.get().strip()
    if not query:
        messagebox.showinfo("没有检索词", "先预览并编辑检索词。")
        return
    app.search_query_var.set(query)
    app._show_page("search")
    app._set_status("检索词已带入 Search；请确认范围后运行。")


def refresh_reviews(app) -> None:
    review = WatchReviewStore(app.runtime.paths.library_db)
    try:
        items = review.list_items()
    finally:
        review.close()
    app._intelligence_review_items = {str(index): item for index, item in enumerate(items)}
    tree = app.intelligence_review_tree
    tree.delete(*tree.get_children())
    for key, item in app._intelligence_review_items.items():
        tree.insert(
            "",
            "end",
            iid=key,
            values=(
                item.detected_at,
                item.rule_id,
                item.event_type,
                item.publication_number,
                _STATUS_LABELS.get(item.status, item.status),
            ),
        )


def load_review_selection(app) -> None:
    selection = app.intelligence_review_tree.selection()
    if not selection:
        return
    item = app._intelligence_review_items[selection[0]]
    app.intelligence_review_status_var.set(_STATUS_LABELS.get(item.status, "待复核"))
    app.intelligence_review_note_var.set(item.note)


def save_review(app) -> None:
    selection = app.intelligence_review_tree.selection()
    if not selection:
        messagebox.showinfo("未选择事件", "请先选择一条监控事件。")
        return
    item = app._intelligence_review_items[selection[0]]
    review = WatchReviewStore(app.runtime.paths.library_db)
    try:
        review.set_review(
            item,
            status=_LABEL_STATUSES[app.intelligence_review_status_var.get()],
            note=app.intelligence_review_note_var.get(),
        )
    finally:
        review.close()
    refresh_reviews(app)
    app._set_status(f"已保存复核：{item.publication_number}")
