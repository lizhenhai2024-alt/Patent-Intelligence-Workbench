"""Tkinter desktop application for Patent Intelligence Workbench."""

from __future__ import annotations

import tkinter as tk
from dataclasses import replace
from tkinter import filedialog, messagebox, ttk

from app.acquisition import AcquisitionRequest
from app.core.patent_number import PatentNumberError, normalize_patent_number
from app.desktop.async_runner import TkCallbackQueue, run_async_in_thread
from app.desktop.opening import open_local_path
from app.desktop.presenters import patent_row, watch_history_row, watch_rule_row
from app.desktop.runtime import DesktopRuntime
from app.domain.family import FamilyType, PatentFamily
from app.library.ingest import ingest_download_summary, ingest_family
from app.library.models import LibraryQuery


class PatentWorkbenchApp(tk.Tk):
    def __init__(self, runtime: DesktopRuntime):
        super().__init__()
        self.runtime = runtime
        self._ui_callbacks = TkCallbackQueue(self)
        self._current_family: PatentFamily | None = None
        self._current_acquisition = None

        self.title("Patent Intelligence Workbench")
        self.geometry("1460x900")
        self.minsize(1180, 720)
        self.configure(bg="#F6F7F9")
        self.protocol("WM_DELETE_WINDOW", self._on_close)

        self._configure_style()
        self._build_shell()
        self.refresh_library()
        self.refresh_watch()

    def _configure_style(self) -> None:
        style = ttk.Style(self)
        if "clam" in style.theme_names():
            style.theme_use("clam")

        bg = "#F6F7F9"
        surface = "#FFFFFF"
        border = "#E5E7EB"
        text = "#111827"
        muted = "#6B7280"
        accent = "#111827"
        accent_hover = "#1F2937"
        selected = "#EEF2FF"

        style.configure("TFrame", background=bg)
        style.configure("Surface.TFrame", background=surface)
        style.configure("Card.TFrame", background=surface, relief="flat")
        style.configure("TLabel", background=bg, foreground=text, font=("Segoe UI", 10))
        style.configure("Surface.TLabel", background=surface, foreground=text)
        style.configure(
            "Title.TLabel", background=bg, foreground=text, font=("Segoe UI Semibold", 18)
        )
        style.configure(
            "PageTitle.TLabel", background=bg, foreground=text, font=("Segoe UI Semibold", 15)
        )
        style.configure("Subtle.TLabel", background=bg, foreground=muted, font=("Segoe UI", 9))
        style.configure(
            "SurfaceSubtle.TLabel", background=surface, foreground=muted, font=("Segoe UI", 9)
        )
        style.configure(
            "Status.TLabel",
            background="#111827",
            foreground="#F9FAFB",
            padding=(12, 7),
            font=("Segoe UI", 9),
        )
        style.configure("TButton", font=("Segoe UI Semibold", 9), padding=(12, 7), relief="flat")
        style.map("TButton", background=[("active", "#E5E7EB")])
        style.configure(
            "Accent.TButton",
            background=accent,
            foreground="#FFFFFF",
            borderwidth=0,
            padding=(14, 8),
        )
        style.map(
            "Accent.TButton",
            background=[("active", accent_hover), ("disabled", "#9CA3AF")],
            foreground=[("disabled", "#F3F4F6")],
        )
        style.configure(
            "Ghost.TButton",
            background=surface,
            foreground=text,
            borderwidth=1,
            relief="solid",
            padding=(12, 7),
        )
        style.map("Ghost.TButton", background=[("active", "#F3F4F6")])
        style.configure(
            "TEntry",
            padding=7,
            fieldbackground=surface,
            foreground=text,
            bordercolor=border,
            lightcolor=border,
            darkcolor=border,
        )
        style.configure(
            "TCombobox", padding=6, fieldbackground=surface, foreground=text, bordercolor=border
        )
        style.configure(
            "TSpinbox", padding=6, fieldbackground=surface, foreground=text, bordercolor=border
        )
        style.configure("TCheckbutton", background=surface, foreground=text)
        style.configure("TLabelframe", background=surface, bordercolor=border, relief="solid")
        style.configure(
            "TLabelframe.Label", background=surface, foreground=text, font=("Segoe UI Semibold", 10)
        )
        style.configure(
            "Treeview",
            background=surface,
            fieldbackground=surface,
            foreground=text,
            rowheight=31,
            borderwidth=0,
            relief="flat",
        )
        style.configure(
            "Treeview.Heading",
            background="#F9FAFB",
            foreground="#374151",
            font=("Segoe UI Semibold", 9),
            padding=(8, 8),
            relief="flat",
        )
        style.map("Treeview", background=[("selected", selected)], foreground=[("selected", text)])
        style.map("Treeview.Heading", background=[("active", "#F3F4F6")])
        style.configure(
            "Nav.TButton",
            background="#111827",
            foreground="#9CA3AF",
            borderwidth=0,
            anchor="w",
            padding=(14, 11),
            font=("Segoe UI Semibold", 9),
        )
        style.map(
            "Nav.TButton",
            background=[("active", "#1F2937")],
            foreground=[("active", "#FFFFFF")],
        )
        style.configure(
            "NavActive.TButton",
            background="#FFFFFF",
            foreground="#111827",
            borderwidth=0,
            anchor="w",
            padding=(14, 11),
            font=("Segoe UI Semibold", 9),
        )
        style.map(
            "NavActive.TButton",
            background=[("active", "#F3F4F6")],
            foreground=[("active", "#111827")],
        )
        style.configure(
            "Horizontal.TProgressbar",
            troughcolor="#E5E7EB",
            background="#111827",
            bordercolor="#E5E7EB",
            lightcolor="#111827",
            darkcolor="#111827",
        )

    def _build_shell(self) -> None:
        header = ttk.Frame(self, padding=(18, 14))
        header.pack(fill="x")
        title_wrap = ttk.Frame(header)
        title_wrap.pack(side="left")
        ttk.Label(
            title_wrap,
            text="Patent Intelligence Workbench",
            style="Title.TLabel",
        ).pack(anchor="w")
        ttk.Label(
            title_wrap,
            text="专利检索 · 专利族 · 监控 · 本地知识库",
            style="Subtle.TLabel",
        ).pack(anchor="w", pady=(2, 0))
        self.network_status_var = tk.StringVar(value=self.runtime.search_status)
        ttk.Label(
            header,
            textvariable=self.network_status_var,
            style="Subtle.TLabel",
        ).pack(side="right")

        workspace = tk.Frame(self, bg="#F6F7F9")
        workspace.pack(fill="both", expand=True, padx=(18, 18), pady=(0, 12))

        sidebar = tk.Frame(workspace, bg="#111827", width=190)
        sidebar.pack(side="left", fill="y")
        sidebar.pack_propagate(False)
        tk.Label(
            sidebar,
            text="WORKSPACE",
            bg="#111827",
            fg="#6B7280",
            font=("Segoe UI Semibold", 8),
            anchor="w",
            padx=14,
            pady=12,
        ).pack(fill="x")

        content = ttk.Frame(workspace)
        content.pack(side="left", fill="both", expand=True, padx=(12, 0))

        self.search_tab = ttk.Frame(content, padding=14)
        self.family_tab = ttk.Frame(content, padding=14)
        self.watch_tab = ttk.Frame(content, padding=14)
        self.library_tab = ttk.Frame(content, padding=14)
        self.settings_tab = ttk.Frame(content, padding=14)
        self._pages = {
            "search": self.search_tab,
            "family": self.family_tab,
            "watch": self.watch_tab,
            "library": self.library_tab,
            "settings": self.settings_tab,
        }
        self._nav_buttons = {}
        for key, label in (
            ("search", "⌕   Search"),
            ("family", "◫   Patent Family"),
            ("watch", "◉   Patent Watch"),
            ("library", "▤   Local Library"),
            ("settings", "⚙   Settings"),
        ):
            button = ttk.Button(
                sidebar,
                text=label,
                style="Nav.TButton",
                command=lambda page=key: self._show_page(page),
            )
            button.pack(fill="x", padx=8, pady=2)
            self._nav_buttons[key] = button

        self._build_search_tab()
        self._build_family_tab()
        self._build_watch_tab()
        self._build_library_tab()
        self._build_settings_tab()
        self._show_page("search")

        self.status_var = tk.StringVar(value="就绪")
        ttk.Label(
            self,
            textvariable=self.status_var,
            anchor="w",
            style="Status.TLabel",
        ).pack(fill="x")

    def _show_page(self, page: str) -> None:
        for key, frame in self._pages.items():
            frame.pack_forget()
            self._nav_buttons[key].configure(style="Nav.TButton")
        self._pages[page].pack(fill="both", expand=True)
        self._nav_buttons[page].configure(style="NavActive.TButton")

    def _build_search_tab(self) -> None:
        ttk.Label(self.search_tab, text="Patent Search", style="PageTitle.TLabel").pack(anchor="w")
        ttk.Label(
            self.search_tab,
            text="按专利号、公司、技术主题或公开网页进行检索与采集",
            style="Subtle.TLabel",
        ).pack(anchor="w", pady=(2, 10))
        search_card = ttk.LabelFrame(self.search_tab, text="检索条件", padding=12)
        search_card.pack(fill="x", pady=(0, 10))
        form = ttk.Frame(search_card, style="Surface.TFrame")
        form.pack(fill="x")

        ttk.Label(form, text="检索").grid(row=0, column=0, sticky="w")
        self.search_query_var = tk.StringVar()
        query_entry = ttk.Entry(form, textvariable=self.search_query_var, width=52)
        query_entry.grid(row=1, column=0, padx=(0, 8), sticky="ew")
        query_entry.bind("<Return>", lambda _event: self.run_search())

        ttk.Label(form, text="公司（可选）").grid(row=0, column=1, sticky="w")
        self.search_company_var = tk.StringVar()
        companies = [
            group.display_name
            for group in (
                self.runtime.search_service.company_registry.groups
                if self.runtime.search_service
                else ()
            )
        ]
        self.search_company_box = ttk.Combobox(
            form,
            textvariable=self.search_company_var,
            values=companies,
            width=26,
        )
        self.search_company_box.grid(
            row=1,
            column=1,
            padx=(0, 8),
            sticky="ew",
        )

        ttk.Label(form, text="检索层级").grid(row=0, column=2, sticky="w")
        self.search_scope_var = tk.StringVar(value="悬架与减振器")
        self.search_scope_box = ttk.Combobox(
            form,
            textvariable=self.search_scope_var,
            values=("公司全量", "悬架与减振器", "具体技术主题"),
            state="readonly",
            width=16,
        )
        self.search_scope_box.grid(row=1, column=2, padx=(0, 8), sticky="ew")

        ttk.Label(form, text="国家").grid(row=0, column=3, sticky="w")
        self.search_jurisdiction_var = tk.StringVar(value="CN,JP,EP,US,WO,KR")
        ttk.Entry(
            form,
            textvariable=self.search_jurisdiction_var,
            width=24,
        ).grid(row=1, column=3, padx=(0, 8), sticky="ew")

        self.search_button = ttk.Button(
            form,
            text="搜索",
            command=self.run_search,
            style="Accent.TButton",
        )
        self.search_button.grid(row=1, column=4, sticky="e")

        form.columnconfigure(0, weight=3)
        form.columnconfigure(1, weight=1)
        form.columnconfigure(2, weight=1)
        form.columnconfigure(3, weight=1)

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
        results_card = ttk.LabelFrame(self.search_tab, text="检索结果", padding=8)
        results_card.pack(fill="both", expand=True, pady=(0, 8))
        self.search_tree.master = results_card
        self.search_tree.pack(in_=results_card, fill="both", expand=True)
        self.search_tree.bind("<Double-1>", self._search_to_family)

        actions = ttk.Frame(self.search_tab)
        actions.pack(fill="x", pady=(8, 0))
        ttk.Button(
            actions,
            text="分析选中专利族",
            command=self._search_to_family,
        ).pack(side="left")
        ttk.Button(
            actions,
            text="采集 URL / 文件",
            command=self.acquire_source,
        ).pack(side="left", padx=(8, 0))
        ttk.Button(
            actions,
            text="选择本地文件",
            command=self.choose_acquisition_file,
        ).pack(side="left", padx=(8, 0))
        ttk.Button(
            actions,
            text="保存为证据",
            command=self.save_current_acquisition,
        ).pack(side="left", padx=(8, 0))

        self.acquisition_link_var = tk.StringVar()
        ttk.Entry(
            actions,
            textvariable=self.acquisition_link_var,
            width=24,
        ).pack(side="left", padx=(12, 0))
        ttk.Label(actions, text="关联专利号（可选）").pack(side="left", padx=(4, 0))

        self.acquisition_preview = tk.Text(self.search_tab, height=9, wrap="word")
        self.acquisition_preview.pack(fill="x", pady=(8, 0))
        self.acquisition_preview.insert("1.0", "采集结果将在这里显示 Markdown 预览。")
        self.acquisition_preview.configure(state="disabled")

    def _build_family_tab(self) -> None:
        ttk.Label(self.family_tab, text="Patent Family", style="PageTitle.TLabel").pack(anchor="w")
        ttk.Label(
            self.family_tab,
            text="解析 DOCDB / INPADOC 专利族，并批量归档与下载",
            style="Subtle.TLabel",
        ).pack(anchor="w", pady=(2, 10))
        family_card = ttk.LabelFrame(self.family_tab, text="专利族分析", padding=12)
        family_card.pack(fill="x", pady=(0, 10))
        form = ttk.Frame(family_card, style="Surface.TFrame")
        form.pack(fill="x")

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
            style="Accent.TButton",
        )
        self.family_analyze_button.grid(row=1, column=2, padx=(0, 8))

        ttk.Button(
            form,
            text="加入本地库",
            command=self.add_current_family_to_library,
        ).grid(row=1, column=3, padx=(0, 8))
        self.family_download_button = ttk.Button(
            form,
            text="下载全部专利 PDF",
            command=self.download_current_family,
        )
        self.family_download_button.grid(row=1, column=4)

        columns = ("number", "country", "title", "application", "date")
        self.family_tree = ttk.Treeview(
            self.family_tab,
            columns=columns,
            show="headings",
        )
        for column, title, width in (
            ("number", "公开号", 180),
            ("country", "国家", 70),
            ("title", "标题", 430),
            ("application", "申请号", 180),
            ("date", "公开日", 110),
        ):
            self.family_tree.heading(column, text=title)
            self.family_tree.column(column, width=width, anchor="w")
        self.family_tree.pack(fill="both", expand=True)

        family_summary_card = ttk.Frame(self.family_tab, style="Surface.TFrame", padding=(12, 9))
        family_summary_card.pack(fill="x", pady=(8, 0))
        self.family_summary_var = tk.StringVar(value="尚未加载专利族")
        ttk.Label(
            family_summary_card,
            textvariable=self.family_summary_var,
            style="SurfaceSubtle.TLabel",
        ).pack(fill="x")

        self.family_download_progress = ttk.Progressbar(
            self.family_tab,
            mode="determinate",
            maximum=1,
        )
        self.family_download_progress.pack(fill="x", pady=(8, 2))
        self.family_download_progress_var = tk.StringVar(value="下载状态：等待开始")
        ttk.Label(
            self.family_tab,
            textvariable=self.family_download_progress_var,
            style="Subtle.TLabel",
        ).pack(fill="x")

    def _build_watch_tab(self) -> None:
        ttk.Label(self.watch_tab, text="Patent Watch", style="PageTitle.TLabel").pack(anchor="w")
        ttk.Label(
            self.watch_tab,
            text="持续监控重点公司与技术主题，识别新专利族和新增成员",
            style="Subtle.TLabel",
        ).pack(anchor="w", pady=(2, 10))
        watch_toolbar_card = ttk.LabelFrame(self.watch_tab, text="监控控制", padding=10)
        watch_toolbar_card.pack(fill="x", pady=(0, 10))
        toolbar = ttk.Frame(watch_toolbar_card, style="Surface.TFrame")
        toolbar.pack(fill="x")
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
            style="Accent.TButton",
        )
        self.run_watch_button.pack(side="left", padx=(8, 0))

        ttk.Separator(toolbar, orient="vertical").pack(
            side="left",
            fill="y",
            padx=10,
        )
        ttk.Label(toolbar, text="监控间隔(h)").pack(side="left")
        self.watch_cadence_var = tk.StringVar(value="24")
        ttk.Spinbox(
            toolbar,
            from_=1,
            to=8760,
            textvariable=self.watch_cadence_var,
            width=7,
        ).pack(side="left", padx=(4, 0))
        ttk.Button(
            toolbar,
            text="应用到选中规则",
            command=self.apply_selected_watch_cadence,
        ).pack(side="left", padx=(6, 0))

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
        self.watch_rule_tree.bind(
            "<<TreeviewSelect>>",
            self._load_selected_watch_cadence,
        )

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
        ttk.Label(self.library_tab, text="Local Library", style="PageTitle.TLabel").pack(anchor="w")
        ttk.Label(
            self.library_tab,
            text="本地专利、PDF、标签、项目与 Evidence 的统一研究工作区",
            style="Subtle.TLabel",
        ).pack(anchor="w", pady=(2, 10))
        library_toolbar_card = ttk.LabelFrame(self.library_tab, text="筛选与导出", padding=10)
        library_toolbar_card.pack(fill="x", pady=(0, 10))
        toolbar = ttk.Frame(library_toolbar_card, style="Surface.TFrame")
        toolbar.pack(fill="x")

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
            columns=(
                "number",
                "country",
                "title",
                "company",
                "topic",
                "favorite",
            ),
            show="headings",
            height=13,
            selectmode="browse",
        )
        for column, title, width in (
            ("number", "公开号", 180),
            ("country", "国家", 70),
            ("title", "标题", 410),
            ("company", "公司", 180),
            ("topic", "技术主题", 210),
            ("favorite", "收藏", 60),
        ):
            self.library_tree.heading(column, text=title)
            self.library_tree.column(column, width=width, anchor="w")
        self.library_tree.pack(fill="both", expand=True)
        self.library_tree.bind(
            "<<TreeviewSelect>>",
            self._load_library_detail,
        )

        detail = ttk.LabelFrame(
            self.library_tab,
            text="专利详情 / 本地整理",
            padding=10,
        )
        detail.pack(fill="x", pady=(10, 0))

        self.library_detail_number_var = tk.StringVar()
        self.library_detail_title_var = tk.StringVar()
        self.library_favorite_var = tk.BooleanVar(value=False)
        self.library_tags_var = tk.StringVar()
        self.library_projects_var = tk.StringVar()

        ttk.Label(detail, text="公开号").grid(row=0, column=0, sticky="w")
        ttk.Label(
            detail,
            textvariable=self.library_detail_number_var,
        ).grid(row=0, column=1, sticky="w", padx=(6, 18))
        ttk.Checkbutton(
            detail,
            text="收藏",
            variable=self.library_favorite_var,
        ).grid(row=0, column=2, sticky="w")

        ttk.Label(detail, text="标题").grid(row=1, column=0, sticky="nw")
        ttk.Label(
            detail,
            textvariable=self.library_detail_title_var,
            wraplength=900,
        ).grid(row=1, column=1, columnspan=4, sticky="w", padx=(6, 0))

        ttk.Label(detail, text="标签").grid(row=2, column=0, sticky="w")
        ttk.Entry(
            detail,
            textvariable=self.library_tags_var,
        ).grid(row=2, column=1, columnspan=2, sticky="ew", padx=(6, 14))

        ttk.Label(detail, text="项目").grid(row=2, column=3, sticky="w")
        ttk.Entry(
            detail,
            textvariable=self.library_projects_var,
        ).grid(row=2, column=4, sticky="ew", padx=(6, 0))

        ttk.Label(detail, text="备注").grid(row=3, column=0, sticky="nw")
        self.library_note_text = tk.Text(detail, height=3, wrap="word")
        self.library_note_text.grid(
            row=3,
            column=1,
            columnspan=4,
            sticky="ew",
            padx=(6, 0),
            pady=(5, 0),
        )

        ttk.Label(detail, text="本地 PDF").grid(row=4, column=0, sticky="nw")
        self.library_pdf_list = tk.Listbox(detail, height=3)
        self.library_pdf_list.grid(
            row=4,
            column=1,
            columnspan=4,
            sticky="ew",
            padx=(6, 0),
            pady=(5, 0),
        )

        ttk.Label(detail, text="关联证据").grid(row=5, column=0, sticky="nw")
        evidence_panel = ttk.Frame(detail)
        evidence_panel.grid(row=5, column=1, columnspan=4, sticky="ew", padx=(6, 0), pady=(5, 0))
        self.library_evidence_list = tk.Listbox(
            evidence_panel,
            height=6,
            borderwidth=0,
            highlightthickness=1,
            highlightbackground="#E5E7EB",
            selectbackground="#EEF2FF",
            selectforeground="#111827",
            font=("Segoe UI", 9),
        )
        self.library_evidence_list.pack(side="left", fill="both", expand=True)
        self.library_evidence_list.bind("<<ListboxSelect>>", self._load_selected_evidence)
        self.library_evidence_preview = tk.Text(
            evidence_panel,
            height=6,
            width=58,
            wrap="word",
            borderwidth=0,
            highlightthickness=1,
            highlightbackground="#E5E7EB",
            background="#F9FAFB",
            foreground="#374151",
            font=("Segoe UI", 9),
            padx=10,
            pady=8,
        )
        self.library_evidence_preview.pack(side="left", fill="both", expand=True, padx=(8, 0))
        self.library_evidence_preview.configure(state="disabled")
        self._library_evidence_records = ()

        actions = ttk.Frame(detail)
        actions.grid(row=6, column=1, columnspan=4, sticky="w", pady=(8, 0))
        ttk.Button(
            actions,
            text="保存详情",
            command=self.save_library_detail,
            style="Accent.TButton",
        ).pack(side="left")
        ttk.Button(
            actions,
            text="打开 PDF",
            command=self.open_selected_library_pdf,
        ).pack(side="left", padx=(8, 0))
        ttk.Button(
            actions,
            text="打开所在目录",
            command=self.open_selected_library_folder,
        ).pack(side="left", padx=(8, 0))

        detail.columnconfigure(1, weight=2)
        detail.columnconfigure(2, weight=1)
        detail.columnconfigure(4, weight=2)

    def _build_settings_tab(self) -> None:
        credentials = self.runtime.current_epo_credentials()

        frame = ttk.LabelFrame(
            self.settings_tab,
            text="EPO Open Patent Services",
            padding=12,
        )
        frame.pack(fill="x")

        self.epo_key_var = tk.StringVar(value=credentials.consumer_key if credentials else "")
        self.epo_secret_var = tk.StringVar(value=credentials.consumer_secret if credentials else "")
        self.settings_status_var = tk.StringVar(value=self.runtime.search_status)

        ttk.Label(frame, text="Consumer Key").grid(
            row=0,
            column=0,
            sticky="w",
        )
        ttk.Entry(
            frame,
            textvariable=self.epo_key_var,
            width=56,
        ).grid(row=1, column=0, padx=(0, 10), sticky="ew")

        ttk.Label(frame, text="Consumer Secret").grid(
            row=0,
            column=1,
            sticky="w",
        )
        ttk.Entry(
            frame,
            textvariable=self.epo_secret_var,
            show="●",
            width=56,
        ).grid(row=1, column=1, padx=(0, 10), sticky="ew")

        self.save_credentials_button = ttk.Button(
            frame,
            text="安全保存",
            command=self.save_epo_settings,
        )
        self.save_credentials_button.grid(row=1, column=2, padx=(0, 8))
        if not self.runtime.credential_store.persistent_available:
            self.save_credentials_button.state(["disabled"])

        ttk.Button(
            frame,
            text="删除已保存凭据",
            command=self.delete_epo_settings,
        ).grid(row=1, column=3)

        ttk.Label(
            frame,
            textvariable=self.settings_status_var,
            style="Subtle.TLabel",
        ).grid(row=2, column=0, columnspan=4, sticky="w", pady=(10, 0))

        frame.columnconfigure(0, weight=1)
        frame.columnconfigure(1, weight=1)

        local = ttk.LabelFrame(
            self.settings_tab,
            text="本地数据",
            padding=12,
        )
        local.pack(fill="x", pady=(12, 0))
        ttk.Label(
            local,
            text=str(self.runtime.paths.root),
        ).pack(side="left", fill="x", expand=True)
        ttk.Button(
            local,
            text="打开数据目录",
            command=lambda: open_local_path(self.runtime.paths.root),
        ).pack(side="right")

        note = (
            "Windows：凭据保存在系统 Credential Manager；不会写入 SQLite、JSON 或 Git 仓库。"
            if self.runtime.credential_store.persistent_available
            else "当前平台不提供桌面持久化凭据；可通过环境变量 "
            "EPO_OPS_KEY / EPO_OPS_SECRET 使用网络功能。"
        )
        ttk.Label(
            self.settings_tab,
            text=note,
            style="Subtle.TLabel",
            wraplength=920,
        ).pack(anchor="w", pady=(12, 0))

    def save_epo_settings(self) -> None:
        key = self.epo_key_var.get().strip()
        secret = self.epo_secret_var.get().strip()
        if not key or not secret:
            messagebox.showinfo(
                "缺少凭据",
                "Consumer Key 和 Consumer Secret 都必须填写。",
            )
            return
        try:
            self.runtime.save_epo_credentials(key, secret)
        except Exception as exc:
            messagebox.showerror("保存失败", str(exc))
            return
        self._refresh_network_controls()
        self._set_status("EPO OPS 凭据已安全保存")

    def delete_epo_settings(self) -> None:
        try:
            self.runtime.delete_epo_credentials()
        except Exception as exc:
            messagebox.showerror("删除失败", str(exc))
            return
        credentials = self.runtime.current_epo_credentials()
        self.epo_key_var.set(credentials.consumer_key if credentials else "")
        self.epo_secret_var.set(credentials.consumer_secret if credentials else "")
        self._refresh_network_controls()
        self._set_status("已删除 Windows Credential Manager 中的 EPO 凭据")

    def _refresh_network_controls(self) -> None:
        self.search_button.state(["!disabled"])
        self.family_analyze_button.state(
            ["!disabled"] if self.runtime.family_resolver else ["disabled"]
        )
        self.run_watch_button.state(["!disabled"] if self.runtime.watch_scheduler else ["disabled"])
        self.network_status_var.set(self.runtime.search_status)
        self.settings_status_var.set(self.runtime.search_status)

        if self.runtime.search_service:
            companies = [
                group.display_name for group in self.runtime.search_service.company_registry.groups
            ]
            self.search_company_box.configure(values=companies)
        else:
            self.search_company_box.configure(values=())

    def _load_library_detail(self, _event=None) -> None:
        selection = self.library_tree.selection()
        if not selection:
            return
        patent = self.runtime.library_store.get_patent(selection[0])
        if patent is None:
            return

        self.library_detail_number_var.set(patent.publication_number)
        self.library_detail_title_var.set(patent.title or "")
        self.library_favorite_var.set(patent.favorite)
        self.library_tags_var.set(", ".join(patent.tags))
        self.library_projects_var.set(", ".join(patent.projects))

        self.library_note_text.delete("1.0", "end")
        self.library_note_text.insert("1.0", patent.note or "")

        self.library_pdf_list.delete(0, "end")
        for path in patent.pdf_paths:
            self.library_pdf_list.insert("end", str(path))

        self._library_evidence_records = self.runtime.library_store.list_evidence(
            publication_number=patent.publication_number,
            limit=100,
        )
        self.library_evidence_list.delete(0, "end")
        for record in self._library_evidence_records:
            label = record.title or record.source
            self.library_evidence_list.insert("end", f"[{record.source_type}] {label}")
        self.library_evidence_preview.configure(state="normal")
        self.library_evidence_preview.delete("1.0", "end")
        if self._library_evidence_records:
            self.library_evidence_list.selection_set(0)
            self._load_selected_evidence()
        self.library_evidence_preview.configure(state="disabled")

    def _load_selected_evidence(self, _event=None) -> None:
        selection = self.library_evidence_list.curselection()
        if not selection:
            return
        record = self._library_evidence_records[selection[0]]
        preview = (
            f"来源：{record.source}\n"
            f"采集时间：{record.captured_at.isoformat()}\n\n"
            f"{record.markdown[:8000]}"
        )
        self.library_evidence_preview.configure(state="normal")
        self.library_evidence_preview.delete("1.0", "end")
        self.library_evidence_preview.insert("1.0", preview)
        self.library_evidence_preview.configure(state="disabled")

    def save_library_detail(self) -> None:
        number = self.library_detail_number_var.get().strip()
        if not number:
            return
        tags = _split_values(self.library_tags_var.get())
        projects = _split_values(self.library_projects_var.get())
        note = self.library_note_text.get("1.0", "end").strip() or None

        store = self.runtime.library_store
        try:
            store.set_favorite(number, self.library_favorite_var.get())
            store.set_note(number, note)
            store.replace_tags(number, tags)
            store.replace_projects(number, projects)
        except Exception as exc:
            messagebox.showerror("保存失败", str(exc))
            return

        self.refresh_library()
        if self.library_tree.exists(number):
            self.library_tree.selection_set(number)
            self.library_tree.see(number)
            self._load_library_detail()
        self._set_status(f"已保存 {number} 的本地库信息")

    def open_selected_library_pdf(self) -> None:
        selection = self.library_pdf_list.curselection()
        if not selection:
            messagebox.showinfo("没有 PDF", "请选择一个本地 PDF。")
            return
        try:
            open_local_path(self.library_pdf_list.get(selection[0]))
        except Exception as exc:
            messagebox.showerror("打开失败", str(exc))

    def open_selected_library_folder(self) -> None:
        selection = self.library_pdf_list.curselection()
        if selection:
            path = self.library_pdf_list.get(selection[0])
            target = __import__("pathlib").Path(path).parent
        else:
            target = self.runtime.paths.downloads
        try:
            open_local_path(target)
        except Exception as exc:
            messagebox.showerror("打开失败", str(exc))

    def choose_acquisition_file(self) -> None:
        path = filedialog.askopenfilename(
            title="选择要采集的文件",
            filetypes=[
                ("Documents", "*.pdf *.docx *.pptx *.xlsx *.html *.htm *.txt"),
                ("All files", "*.*"),
            ],
        )
        if path:
            self.search_query_var.set(path)
            self.acquire_source()

    def acquire_source(self) -> None:
        engine = self.runtime.acquisition_engine
        source = self.search_query_var.get().strip()
        if engine is None or not source:
            messagebox.showinfo("采集", "请输入 URL，或选择本地文件。")
            return
        self._set_status("正在采集并转换为 Markdown…")

        def task():
            return engine.acquire(AcquisitionRequest(source=source))

        run_async_in_thread(
            task,
            on_success=self._render_acquisition_result,
            on_error=lambda exc: self._network_error("采集失败", exc),
            schedule_ui=self._ui_callbacks.submit,
        )

    def _render_acquisition_result(self, result) -> None:
        self._current_acquisition = result
        preview = result.markdown[:12000]
        self.acquisition_preview.configure(state="normal")
        self.acquisition_preview.delete("1.0", "end")
        self.acquisition_preview.insert("1.0", preview)
        self.acquisition_preview.configure(state="disabled")
        if not self.acquisition_link_var.get().strip():
            try:
                normalized = normalize_patent_number(self.search_query_var.get().strip())
            except PatentNumberError:
                normalized = None
            if normalized is not None:
                self.acquisition_link_var.set(normalized.canonical)
        self._set_status(
            f"采集完成：{result.kind.value} · {len(result.markdown)} 字符 · {result.source}"
        )

    def save_current_acquisition(self) -> None:
        result = self._current_acquisition
        if result is None:
            messagebox.showinfo("没有采集结果", "请先采集 URL 或本地文件。")
            return
        try:
            record = self.runtime.library_service.save_acquisition_evidence(
                source=result.source,
                source_type=result.kind.value,
                title=result.title,
                markdown=result.markdown,
                metadata=result.metadata,
                publication_number=self.acquisition_link_var.get().strip() or None,
                company_group=self.search_company_var.get().strip() or None,
                technology_topic=self.search_query_var.get().strip() or None,
            )
        except Exception as exc:
            messagebox.showerror("保存证据失败", str(exc))
            return
        self.refresh_library()
        linked = record.publication_number or "未关联专利"
        self._set_status(f"证据已保存：{record.evidence_id} · {linked}")

    def run_search(self) -> None:
        service = self.runtime.search_service
        if service is None:
            messagebox.showwarning("未配置", self.runtime.search_status)
            return

        query = self.search_query_var.get().strip()
        company = self.search_company_var.get().strip() or None
        scope = self.search_scope_var.get().strip()
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
            resolved_company = company
            resolved_query = query
            if not resolved_company and query:
                try:
                    resolved_company = service.company_registry.get(query).display_name
                    resolved_query = ""
                except KeyError:
                    pass

            portfolio_scope = None
            technology_terms = ()
            if resolved_company:
                if scope == "悬架与减振器":
                    portfolio_scope = "suspension portfolio"
                elif scope == "具体技术主题" and resolved_query:
                    technology_terms = (resolved_query,)
            return service.search(
                resolved_query if not resolved_company or scope == "具体技术主题" else "",
                company=resolved_company,
                portfolio_scope=portfolio_scope,
                technology_terms=technology_terms,
                jurisdictions=jurisdictions,
                page_size=100,
            )

        run_async_in_thread(
            task,
            on_success=self._render_search_response,
            on_error=lambda exc: self._network_error("搜索失败", exc),
            schedule_ui=self._ui_callbacks.submit,
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
            f"搜索完成：{response.provider} · 显示 {len(response.page.hits)} 条"
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
            schedule_ui=self._ui_callbacks.submit,
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
                    member.title or "",
                    member.application_number or "",
                    member.publication_date.isoformat() if member.publication_date else "",
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

        total = len(family.members)
        self.family_download_button.state(["disabled"])
        self.family_download_progress.configure(maximum=max(total, 1), value=0)
        self.family_download_progress_var.set(f"下载状态：准备开始，共 {total} 个专利成员")
        self._set_status(f"正在下载整族 PDF：0 / {total}")

        def progress_callback(progress) -> None:
            self._ui_callbacks.submit(
                lambda item=progress: self._render_family_download_progress(item)
            )

        def task():
            return self.runtime.family_downloader.download_family(
                family,
                self.runtime.paths.downloads,
                on_progress=progress_callback,
            )

        def success(summary) -> None:
            self.family_download_button.state(["!disabled"])
            ingest_family(self.runtime.library_store, family)
            ingest_download_summary(self.runtime.library_store, summary)
            self.refresh_library()
            self.family_download_progress.configure(
                maximum=max(len(summary.members), 1),
                value=len(summary.members),
            )
            self.family_download_progress_var.set(
                f"下载完成：成功 {summary.succeeded}，失败 {summary.failed} · "
                f"{summary.family_folder}"
            )
            self._set_status(f"下载完成：成功 {summary.succeeded}，失败 {summary.failed}")

            if summary.failed:
                failed = [
                    f"{member.publication_number}: {member.error or '未下载'}"
                    for member in summary.members
                    if member.status == "failed"
                ]
                details = "\n".join(failed[:8])
                if len(failed) > 8:
                    details += f"\n…另有 {len(failed) - 8} 项"
                messagebox.showwarning(
                    "整族 PDF 下载完成（有失败）",
                    f"成功 {summary.succeeded}，失败 {summary.failed}\n\n"
                    f"目录：{summary.family_folder}\n\n{details}",
                )
            else:
                messagebox.showinfo(
                    "整族 PDF 下载完成",
                    f"成功下载 {summary.succeeded} 个专利 PDF。\n\n目录：{summary.family_folder}",
                )

        def failed(exc: Exception) -> None:
            self.family_download_button.state(["!disabled"])
            self.family_download_progress_var.set(f"下载失败：{exc}")
            self._network_error("下载失败", exc)

        run_async_in_thread(
            task,
            on_success=success,
            on_error=failed,
            schedule_ui=self._ui_callbacks.submit,
        )

    def _render_family_download_progress(self, progress) -> None:
        self.family_download_progress.configure(
            maximum=max(progress.total, 1),
            value=progress.completed,
        )
        state = "成功" if progress.status == "success" else "失败"
        self.family_download_progress_var.set(
            f"下载中：{progress.completed} / {progress.total} · "
            f"{progress.publication_number} · {state}"
        )
        self._set_status(
            f"正在下载整族 PDF：{progress.completed} / {progress.total} · "
            f"{progress.publication_number}"
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
        self.runtime.watch_store.upsert_rule(replace(rule, enabled=not rule.enabled))
        self.refresh_watch()

    def _load_selected_watch_cadence(self, _event=None) -> None:
        selection = self.watch_rule_tree.selection()
        if not selection:
            return
        rule = self.runtime.watch_store.get_rule(selection[0])
        if rule is not None:
            self.watch_cadence_var.set(str(rule.cadence_hours))

    def apply_selected_watch_cadence(self) -> None:
        selection = self.watch_rule_tree.selection()
        if not selection:
            messagebox.showinfo("未选择规则", "请先选择一条 Patent Watch 规则。")
            return

        try:
            cadence_hours = int(self.watch_cadence_var.get().strip())
        except ValueError:
            messagebox.showerror("间隔错误", "监控间隔必须是整数小时。")
            return
        if cadence_hours < 1 or cadence_hours > 8760:
            messagebox.showerror("间隔错误", "监控间隔必须在 1–8760 小时之间。")
            return

        rule = self.runtime.watch_store.get_rule(selection[0])
        if rule is None:
            return
        self.runtime.watch_store.upsert_rule(replace(rule, cadence_hours=cadence_hours))
        self.refresh_watch()
        if self.watch_rule_tree.exists(rule.rule_id):
            self.watch_rule_tree.selection_set(rule.rule_id)
            self.watch_rule_tree.focus(rule.rule_id)
        self.watch_cadence_var.set(str(cadence_hours))
        self._set_status(f"Patent Watch 间隔已更新：{rule.name} → {cadence_hours} 小时")

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
            schedule_ui=self._ui_callbacks.submit,
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
        if hasattr(self, "family_download_button"):
            self.family_download_button.state(["!disabled"])
        self.run_watch_button.state(["!disabled"])
        self._set_status(f"{title}: {exc}")
        messagebox.showerror(title, str(exc))

    def _set_status(self, text: str) -> None:
        self.status_var.set(text)

    def _on_close(self) -> None:
        self._ui_callbacks.close()
        self.runtime.close()
        self.destroy()


def _split_values(value: str) -> tuple[str, ...]:
    normalized = value.replace("，", ",").replace(";", ",").replace("；", ",")
    return tuple(dict.fromkeys(item.strip() for item in normalized.split(",") if item.strip()))


def run_desktop(runtime: DesktopRuntime | None = None) -> None:
    resolved_runtime = runtime or DesktopRuntime.create()
    app = PatentWorkbenchApp(resolved_runtime)
    app.mainloop()
