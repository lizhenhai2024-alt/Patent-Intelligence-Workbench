"""Desktop entry point for local engineering-intelligence workflows."""

from __future__ import annotations

import threading
import tkinter as tk
from datetime import date
from tkinter import filedialog, messagebox, ttk

from app.desktop.opening import open_local_path
from app.intelligence.ai_packet import build_ai_prompt
from app.intelligence.analysis import AnalysisReport, AnalysisScope, AnalysisService
from app.intelligence.report import save_html
from app.intelligence.search_plan import plan_search
from app.intelligence.watch_review import ReviewItem, WatchReviewStore

_WORKFLOWS = (
    "专利全景分析",
    "公司技术画像",
    "竞争格局分析",
    "技术路线对比",
    "工程问题检索",
    "新专利监控简报",
)
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
        text="基于当前 LocalLibrary 的离线分析；统计数字可追溯到原始公开件",
        style="Subtle.TLabel",
    ).pack(anchor="w", pady=(2, 12))

    form = ttk.LabelFrame(page, text="任务条件", padding=12)
    form.pack(fill="x")
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

    fields = (
        ("工作流", app.intelligence_workflow_var),
        ("技术主题 / 工程问题", app.intelligence_topic_var),
        ("公司组（画像填 1 家，竞争填至少 2 家；逗号分隔）", app.intelligence_companies_var),
        ("技术路线（对比填至少 2 条节点 ID；逗号分隔）", app.intelligence_routes_var),
        ("国家/局（如 CN,JP,US）", app.intelligence_countries_var),
        ("起始年份", app.intelligence_start_var),
        ("结束年份", app.intelligence_end_var),
    )
    for index, (label, variable) in enumerate(fields):
        row, col = divmod(index, 2)
        cell = ttk.Frame(form)
        cell.grid(row=row, column=col, sticky="ew", padx=(0, 16), pady=5)
        ttk.Label(cell, text=label).pack(anchor="w")
        if index == 0:
            ttk.Combobox(cell, textvariable=variable, values=_WORKFLOWS, state="readonly").pack(
                fill="x"
            )
        else:
            ttk.Entry(cell, textvariable=variable).pack(fill="x")
    form.columnconfigure(0, weight=1)
    form.columnconfigure(1, weight=1)

    buttons = ttk.Frame(page)
    buttons.pack(fill="x", pady=10)
    ttk.Button(buttons, text="运行任务", command=lambda: run_task(app)).pack(side="left")
    ttk.Button(buttons, text="保存离线 HTML", command=lambda: save_report(app)).pack(
        side="left", padx=8
    )
    ttk.Button(buttons, text="复制 AI 解读提示词", command=lambda: copy_ai_prompt(app)).pack(
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

    app.intelligence_preview = tk.Text(page, height=11, wrap="word", state="disabled")
    app.intelligence_preview.pack(fill="both", expand=True)

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
    refresh_reviews(app)


def _preview(app, text: str) -> None:
    widget = app.intelligence_preview
    widget.configure(state="normal")
    widget.delete("1.0", "end")
    widget.insert("1.0", text)
    widget.configure(state="disabled")


def run_task(app) -> None:
    workflow = app.intelligence_workflow_var.get()
    topic = app.intelligence_topic_var.get().strip()
    companies = _split(app.intelligence_companies_var.get())
    routes = _split(app.intelligence_routes_var.get())
    try:
        scope = AnalysisScope(
            topic="" if workflow in ("工程问题检索", "新专利监控简报") else topic,
            jurisdictions=_split(app.intelligence_countries_var.get()),
            from_date=_year(app.intelligence_start_var.get(), end=False),
            to_date=_year(app.intelligence_end_var.get(), end=True),
        )
        if workflow == "工程问题检索":
            plan = plan_search(topic)
            app.intelligence_query_var.set(plan.editable_query)
            lines = [f"问题：{plan.problem}", "建议词组（请编辑后自行运行检索）："]
            lines += [
                f"{group.topic_name} [{group.source}]：{' / '.join(group.terms)}"
                for group in plan.groups
            ]
            if plan.unmatched:
                lines.append("词典未识别该问题；保留原问题供人工编辑。")
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
            if workflow == "新专利监控简报":
                review = WatchReviewStore(app.runtime.paths.library_db)
                try:
                    report = review.brief()
                finally:
                    review.close()
            else:
                service = AnalysisService(app.runtime.library_store)
                if workflow == "专利全景分析":
                    report = service.landscape(scope)
                elif workflow == "公司技术画像":
                    if len(companies) != 1:
                        raise ValueError("公司技术画像需填写一家已登记公司")
                    report = service.company_profile(scope, companies[0])
                elif workflow == "竞争格局分析":
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
    lines.append("\n保存 HTML 可逐项展开来源公开件与统计口径。")
    _preview(app, "\n".join(lines))
    app._set_status(f"已生成：{report.title}")
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
