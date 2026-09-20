"""Tkinter desktop application for Patent Intelligence Workbench."""

from __future__ import annotations

from dataclasses import replace
from pathlib import Path
import tkinter as tk
from tkinter import filedialog, messagebox, ttk

from app.core.patent_number import PatentNumberError, normalize_patent_number
from app.desktop.async_runner import run_async_in_thread
from app.desktop.presenters import patent_row, watch_history_row, watch_rule_row
from app.desktop.runtime import DesktopRuntime
from app.domain.family import FamilyType, PatentFamily
from app.library.ingest import ingest_download_summary, ingest_family
from app.library.models import LibraryQuery


class PatentWorkbenchApp(tk.Tk):
    def __init__(self, runtime: DesktopRuntime):
        super().__init__()
        self.runtime = runtime
        self._current_family: PatentFamily | None = None

        self.title("Patent Intelligence Workbench")
        self.geometry("1280x820")
        self.minsize(1000, 650)
        self.protocol("WM_DELETE_WINDOW", self._on_close)

        self._configure_style()
        self._build_shell()
        self.refresh_library()
        self.refresh_watch()

    def _configure_style(self) -> None:
        style = ttk.Style(self)
        if "clam" in style.theme_names():
            style.theme_use("clam")
        style.configure("Title.TLabel", font=("Segoe UI", 16, "bold"))
        style.configure("Subtle.TLabel", foreground="#555555")
        style.configure("Treeview", rowheight=26)
        style.configure("Treeview.Heading", font=("Segoe UI", 9, "bold"))

    def _build_shell(self) -> None:
        header = ttk.Frame(self, padding=(14, 10))
        header.pack(fill="x")
        ttk.Label(
            header,
            text="Patent Intelligence Workbench",
            style="Title.TLabel",
        ).pack(side="left")
        ttk.Label(
            header,
            text=self.runtime.search_status,
            style="Subtle.TLabel",
        ).pack(side="right")

        self.notebook = ttk.Notebook(self)
        self.notebook.pack(fill="both", expand=True, padx=10, pady=(0, 8))

        self.search_tab = ttk.Frame(self.notebook, padding=10)
        self.family_tab = ttk.Frame(self.notebook, padding=10)
        self.watch_tab = ttk.Frame(self.notebook, padding=10)
        self.library_tab = ttk.Frame(self.notebook, padding=10)

        self.notebook.add(self.search_tab, text="Search")
        self.notebook.add(self.family_tab, text="Family")
        self.notebook.add(self.watch_tab, text="Patent Watch")
        self.notebook.add(self.library_tab, text="Local Library")

        self._build_search_tab()
        self._build_family_tab()
        self._build_watch_tab()
        self._build_library_tab()

        self.status_var = tk.StringVar(value="就绪")
        ttk.Label(
            self,
            textvariable=self.status_var,
            anchor="w",
            padding=(10, 4),
        ).pack(fill="x")

    def _build_search_tab(self) -> None:
        form = ttk.Frame(self.search_tab)
        form.pack(fill="x", pady=(0, 8))

        ttk.Label(form, text="检索").grid(row=0, column=0, sticky="w")
        self.search_query_var = tk.StringVar()
        query_entry = ttk.Entry(form, textvariable=self.search_query_var, width=52)
        query_entry.grid(row=1, column=0, padx=(0, 8), sticky="ew")
        query_entry.bind("<Return>", lambda _event: self.run_search())

        ttk.Label(form, text="公司（可选）").grid(row=0, column=1, sticky="w")
        self.search_company_var = tk.StringVar()
        companies = [
            group.display_name
            for group in self.runtime.search_service.company_registry.groups
        ] if self.runtime.search_service else []
        company_box = ttk.Combobox(
            form,
            textvariable=self.search_company_var,
            values=companies,
            width=26,
        )
        company_box.grid(row=1, column=1, padx=(0, 8), sticky="ew")

        ttk.Label(form, text="国家").grid(row=0, column=2, sticky="w")
        self.search_jurisdiction_var = tk.StringVar(
            value="CN,JP,EP,US,WO,KR"
        )
        ttk.Entry(
            form,
            textvariable=self.search_jurisdiction_var,
            width=24,
        ).grid(row=1, column=2, padx=(0, 8), sticky="ew")

        self.search_button = ttk.Button(
            form,
            text="搜索",
            command=self.run_search,
        )
        self.search_button.grid(row=1, column=3, sticky="e")
        if self.runtime.search_service is None:
            self.search_button.state(["disabled"])

        form.columnconfigure(0, weight=3)
        form.columnconfigure(1, weight=1)
        form.columnconfigure(2, weight=1)

        columns = ("number", "country", "title", "applicant", "date")
        self.search_tree = ttk.Treeview(
            self.search_tab,
            columns=columns,
            show="headings",
            selectmode="browse",
        )
        headings = {
            "number": "公开号",
            "country": "国家",
            "title": "标题",
            "applicant": "申请人",
            "date": "公开日",
        }
        widths = {
            "number": 170,
            "country": 70,
            "title": 430,
            "applicant": 300,
            "date": 100,
        }
        for column in columns:
            self.search_tree.heading(column, text=headings[column])
            self.search_tree.column(column, width=widths[column], anchor="w")
        self.search_tree.pack(fill="both", expand=True)
        self.search_tree.bind("<Double-1>", self._search_to_family)

        actions = ttk.Frame(self.search_tab)
        actions.pack(fill="x", pady=(8, 0))
        ttk.Button(
            actions,
            text="分析选中专利族",
            command=self._search_to_family,
        ).pack(side="left")

    def _build_family_tab(self) -> None:
        form = ttk.Frame(self.family_tab)
        form.pack(fill="x", pady=(0, 8))

        self.family_number_var = tk.StringVar()
        ttk.Label(form, text="公开号").grid(row=0, column=0, sticky="w")
        ttk.Entry(
            form,
            textvariable=self.family_number_var,
            width=34,
        ).grid(row=1, column=0, padx=(0, 8), sticky="ew")

        self.family_type_var = tk.StringVar(value=FamilyType.DOCDB_SIMPLE.value)
        ttk.Label(form, text="Family 类型").grid(row=0, column=1, sticky="w")
        ttk.Combobox(
            form,
            textvariable=self.family_type_var,
            values=[
                FamilyType.DOCDB_SIMPLE.value,
                FamilyType.INPADOC_EXTENDED.value,
            ],
            state="readonly",
            width=24,
        ).grid(row=1, column=1, padx=(0, 8))

        self.family_analyze_button = ttk.Button(
            form,
            text="分析专利族",
            command=self.run_family_analysis,
        )
        self.family_analyze_button.grid(row=1, column=2, padx=(0, 8))
        if self.runtime.family_resolver is None:
            self.family_analyze_button.state(["disabled"])

        ttk.Button(
            form,
            text="加入本地库",
            command=self.add_current_family_to_library,
        ).grid(row=1, column=3, padx=(0, 8))
        ttk.Button(
            form,
            text="下载整族 PDF",
            command=self.download_current_family,
        ).grid(row=1, column=4)

        columns = ("number", "country", "application", "date")
        self.family_tree = ttk.Treeview(
            self.family_tab,
            columns=columns,
            show="headings",
        )
        for column, title, width in (
            ("number", "公开号", 210),
            ("country", "国家", 80),
            ("application", "申请号", 210),
            ("date", "公开日", 120),
        ):
            self.family_tree.heading(column, text=title)
            self.family_tree.column(column, width=width, anchor="w")
        self.family_tree.pack(fill="both", expand=True)

        self.family_summary_var = tk.StringVar(value="尚未加载专利族")
        ttk.Label(
            self.family_tab,
            textvariable=self.family_summary_var,
            style="Subtle.TLabel",
        ).pack(fill="x", pady=(8, 0))

    def _build_watch_tab(self) -> None:
        toolbar = ttk.Frame(self.watch_tab)
        toolbar.pack(fill="x", pady=(0, 8))
        ttk.Button(
            toolbar,
            text="刷新",
            command=self.refresh_watch,
        ).pack(side="left")
        ttk.Button(
            toolbar,
            text="切换启用状态",
            command=self.toggle_selected_watch_rule,
        ).pack(side="left", padx=(8, 0))
        self.run_watch_button = ttk.Button(
            toolbar,
            text="运行到期规则",
            command=self.run_due_watch_rules,
        )
        self.run_watch_button.pack(side="left", padx=(8, 0))
        if self.runtime.watch_scheduler is None:
            self.run_watch_button.state(["disabled"])

        self.watch_rule_tree = ttk.Treeview(
            self.watch_tab,
            columns=("name", "enabled", "cadence", "last_run", "company"),
            show="headings",
            height=13,
            selectmode="browse",
        )
        for column, title, width in (
            ("name", "规则", 330),
            ("enabled", "状态", 80),
            ("cadence", "周期", 80),
            ("last_run", "上次运行", 190),
            ("company", "公司", 150),
        ):
            self.watch_rule_tree.heading(column, text=title)
            self.watch_rule_tree.column(column, width=width, anchor="w")
        self.watch_rule_tree.pack(fill="both", expand=True)

        ttk.Label(
            self.watch_tab,
            text="最近运行",
            style="Subtle.TLabel",
        ).pack(anchor="w", pady=(10, 4))

        self.watch_history_tree = ttk.Treeview(
            self.watch_tab,
            columns=("rule", "status", "time", "events", "error"),
            show="headings",
            height=8,
        )
        for column, title, width in (
            ("rule", "Rule ID", 260),
            ("status", "状态", 80),
            ("time", "时间", 190),
            ("events", "事件", 70),
            ("error", "错误", 420),
        ):
            self.watch_history_tree.heading(column, text=title)
            self.watch_history_tree.column(column, width=width, anchor="w")
        self.watch_history_tree.pack(fill="both", expand=True)

    def _build_library_tab(self) -> None:
        toolbar = ttk.Frame(self.library_tab)
        toolbar.pack(fill="x", pady=(0, 8))

        self.library_query_var = tk.StringVar()
        entry = ttk.Entry(
            toolbar,
            textvariable=self.library_query_var,
            width=48,
        )
        entry.pack(side="left")
        entry.bind("<Return>", lambda _event: self.refresh_library())

        ttk.Button(
            toolbar,
            text="筛选",
            command=self.refresh_library,
        ).pack(side="left", padx=(8, 0))
        ttk.Button(
            toolbar,
            text="导出 CSV",
            command=lambda: self.export_library(".csv"),
        ).pack(side="left", padx=(8, 0))
        ttk.Button(
            toolbar,
            text="导出 Excel",
            command=lambda: self.export_library(".xlsx"),
        ).pack(side="left", padx=(8, 0))

        self.library_tree = ttk.Treeview(
            self.library_tab,
            columns=("number", "country", "title", "company", "topic", "favorite"),
            show="headings",
        )
        for column, title, width in (
            ("number", "公开号", 180),
            ("country", "国家", 70),
            ("title", "标题", 420),
            ("company", "公司", 190),
            ("topic", "技术主题", 220),
            ("favorite", "收藏", 60),
        ):
            self.library_tree.heading(column, text=title)
            self.library_tree.column(column, width=width, anchor="w")
        self.library_tree.pack(fill="both", expand=True)

    def run_search(self) -> None:
        service = self.runtime.search_service
        if service is None:
            messagebox.showwarning("未配置", self.runtime.search_status)
            return

        query = self.search_query_var.get().strip()
        company = self.search_company_var.get().strip() or None
        jurisdictions = tuple(
            item.strip().upper()
            for item in self.search_jurisdiction_var.get().split(",")
            if item.strip()
        )
        if not query and not company:
            messagebox.showinfo("请输入条件", "请输入专利号、关键词或公司。")
            return

        self.search_button.state(["disabled"])
        self._set_status("正在搜索…")

        def task():
            return service.search(
                query,
                company=company,
                technology_terms=(query,) if company and query else (),
                jurisdictions=jurisdictions,
                page_size=100,
            )

        run_async_in_thread(
            task,
            on_success=self._render_search_response,
            on_error=lambda exc: self._network_error("搜索失败", exc),
            schedule_ui=lambda callback: self.after(0, callback),
        )

    def _render_search_response(self, response) -> None:
        self.search_button.state(["!disabled"])
        self.search_tree.delete(*self.search_tree.get_children())
        for hit in response.page.hits:
            self.search_tree.insert(
                "",
                "end",
                iid=hit.publication_number,
                values=(
                    hit.publication_number,
                    hit.jurisdiction,
                    hit.title or "",
                    ", ".join(hit.applicants),
                    hit.publication_date.isoformat() if hit.publication_date else "",
                ),
            )
        total = response.page.total_result_count
        self._set_status(
            f"搜索完成：显示 {len(response.page.hits)} 条"
            + (f" / 共 {total} 条" if total is not None else "")
        )

    def _search_to_family(self, _event=None) -> None:
        selection = self.search_tree.selection()
        if not selection:
            return
        self.family_number_var.set(selection[0])
        self.notebook.select(self.family_tab)
        if self.runtime.family_resolver is not None:
            self.run_family_analysis()

    def run_family_analysis(self) -> None:
        resolver = self.runtime.family_resolver
        if resolver is None:
            messagebox.showwarning("未配置", self.runtime.search_status)
            return

        try:
            publication = normalize_patent_number(self.family_number_var.get())
        except PatentNumberError as exc:
            messagebox.showerror("专利号错误", str(exc))
            return

        family_type = FamilyType(self.family_type_var.get())
        self.family_analyze_button.state(["disabled"])
        self._set_status("正在解析专利族…")

        def task():
            return resolver.resolve(publication, family_type)

        run_async_in_thread(
            task,
            on_success=self._render_family_resolution,
            on_error=lambda exc: self._network_error("专利族解析失败", exc),
            schedule_ui=lambda callback: self.after(0, callback),
        )

    def _render_family_resolution(self, resolution) -> None:
        self.family_analyze_button.state(["!disabled"])
        family = resolution.family
        self._current_family = family
        self.family_tree.delete(*self.family_tree.get_children())
        for member in family.members:
            self.family_tree.insert(
                "",
                "end",
                iid=member.publication_number,
                values=(
                    member.publication_number,
                    member.jurisdiction,
                    member.application_number or "",
                    member.publication_date.isoformat()
                    if member.publication_date
                    else "",
                ),
            )
        priority = family.earliest_priority
        self.family_summary_var.set(
            f"{family.family_type.value} · {len(family.members)} 成员 · "
            f"Family ID: {family.source_family_id or '-'} · "
            f"最早优先权: {priority.number if priority else '-'}"
        )
        self._set_status(f"专利族解析完成：{len(family.members)} 个成员")

    def add_current_family_to_library(self) -> None:
        family = self._current_family
        if family is None:
            messagebox.showinfo("没有专利族", "请先分析一个专利族。")
            return
        ingest_family(self.runtime.library_store, family)
        self.refresh_library()
        self._set_status("专利族已加入本地库")

    def download_current_family(self) -> None:
        family = self._current_family
        if family is None:
            messagebox.showinfo("没有专利族", "请先分析一个专利族。")
            return
        self._set_status("正在下载整族 PDF…")

        def task():
            return self.runtime.family_downloader.download_family(
                family,
                self.runtime.paths.downloads,
            )

        def success(summary) -> None:
            ingest_family(self.runtime.library_store, family)
            ingest_download_summary(self.runtime.library_store, summary)
            self.refresh_library()
            self._set_status(
                f"下载完成：成功 {summary.succeeded}，失败 {summary.failed}"
            )
            if summary.failed:
                messagebox.showwarning(
                    "部分下载失败",
                    "部分成员未自动下载，可在 family.json 中查看官方替代来源。",
                )

        run_async_in_thread(
            task,
            on_success=success,
            on_error=lambda exc: self._network_error("下载失败", exc),
            schedule_ui=lambda callback: self.after(0, callback),
        )

    def refresh_watch(self) -> None:
        self.watch_rule_tree.delete(*self.watch_rule_tree.get_children())
        for rule in self.runtime.watch_store.list_rules():
            state = self.runtime.watch_store.get_state(rule.rule_id)
            self.watch_rule_tree.insert(
                "",
                "end",
                iid=rule.rule_id,
                values=watch_rule_row(rule, state),
            )

        self.watch_history_tree.delete(*self.watch_history_tree.get_children())
        for history in self.runtime.watch_store.recent_runs(limit=30):
            self.watch_history_tree.insert(
                "",
                "end",
                values=watch_history_row(history),
            )

    def toggle_selected_watch_rule(self) -> None:
        selection = self.watch_rule_tree.selection()
        if not selection:
            return
        rule_id = selection[0]
        rule = self.runtime.watch_store.get_rule(rule_id)
        if rule is None:
            return
        self.runtime.watch_store.upsert_rule(
            replace(rule, enabled=not rule.enabled)
        )
        self.refresh_watch()

    def run_due_watch_rules(self) -> None:
        scheduler = self.runtime.watch_scheduler
        if scheduler is None:
            messagebox.showwarning("未配置", self.runtime.search_status)
            return
        self.run_watch_button.state(["disabled"])
        self._set_status("正在运行到期监控规则…")

        def task():
            return scheduler.run_due()

        def success(result) -> None:
            self.run_watch_button.state(["!disabled"])
            self.refresh_watch()
            event_count = sum(len(run.events) for run in result.runs)
            self._set_status(
                f"监控完成：{len(result.runs)} 成功，"
                f"{len(result.failures)} 失败，{event_count} 个事件"
            )

        run_async_in_thread(
            task,
            on_success=success,
            on_error=lambda exc: self._network_error("监控失败", exc),
            schedule_ui=lambda callback: self.after(0, callback),
        )

    def refresh_library(self) -> None:
        query = LibraryQuery(
            text=self.library_query_var.get().strip()
            if hasattr(self, "library_query_var")
            else None,
            limit=1000,
        )
        patents = self.runtime.library_service.search(query)
        if not hasattr(self, "library_tree"):
            return
        self.library_tree.delete(*self.library_tree.get_children())
        for patent in patents:
            self.library_tree.insert(
                "",
                "end",
                iid=patent.publication_number,
                values=patent_row(patent),
            )
        if hasattr(self, "status_var"):
            self._set_status(f"本地库：{len(patents)} 条")

    def export_library(self, suffix: str) -> None:
        default_name = f"patent-library{suffix}"
        path = filedialog.asksaveasfilename(
            defaultextension=suffix,
            initialdir=self.runtime.paths.exports,
            initialfile=default_name,
            filetypes=[
                ("Excel", "*.xlsx"),
                ("CSV", "*.csv"),
                ("All files", "*.*"),
            ],
        )
        if not path:
            return
        query = LibraryQuery(
            text=self.library_query_var.get().strip() or None,
            limit=10000,
        )
        result = self.runtime.library_service.export(path, query=query)
        self._set_status(f"已导出：{result}")

    def _network_error(self, title: str, exc: Exception) -> None:
        self.search_button.state(["!disabled"])
        self.family_analyze_button.state(["!disabled"])
        self.run_watch_button.state(["!disabled"])
        self._set_status(f"{title}: {exc}")
        messagebox.showerror(title, str(exc))

    def _set_status(self, text: str) -> None:
        self.status_var.set(text)

    def _on_close(self) -> None:
        self.runtime.close()
        self.destroy()


def run_desktop(runtime: DesktopRuntime | None = None) -> None:
    resolved_runtime = runtime or DesktopRuntime.create()
    app = PatentWorkbenchApp(resolved_runtime)
    app.mainloop()
