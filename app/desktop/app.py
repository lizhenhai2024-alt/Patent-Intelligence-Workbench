"""Tkinter desktop application for Patent Intelligence Workbench."""

from __future__ import annotations

import base64
import tkinter as tk
import webbrowser
from dataclasses import replace
from tkinter import filedialog, messagebox, ttk

import httpx

from app.acquisition import AcquisitionRequest
from app.core.patent_number import PatentNumberError, normalize_patent_number
from app.core.technology_classifier import TechnologyClassifier
from app.core.technology_taxonomy import TechnologyTaxonomy
from app.core.translation import UnconfiguredTranslationProvider
from app.core.translation_http import CachedTranslationProvider, HttpTranslationProvider
from app.desktop.async_runner import TkCallbackQueue, run_async_in_thread
from app.desktop.figure_preview import figure_scale
from app.desktop.opening import open_local_path
from app.desktop.presenters import patent_row, watch_history_row, watch_rule_row
from app.desktop.runtime import DesktopRuntime
from app.desktop.translation_config import (
    TranslationSettings,
    delete_translation_settings,
    load_translation_settings,
    save_translation_settings,
)
from app.domain.family import FamilyType, PatentFamily, PatentPublication
from app.domain.reader import PatentReaderDocument
from app.library.archive import patent_archive_path
from app.library.ingest import ingest_download_summary, ingest_family
from app.library.models import LibraryQuery
from app.library.root_sync import sync_library_root
from app.providers.google_patents_search import GooglePatentsSearchProvider


class PatentWorkbenchApp(tk.Tk):
    def __init__(self, runtime: DesktopRuntime):
        super().__init__()
        self.runtime = runtime
        self._ui_callbacks = TkCallbackQueue(self)
        self._current_family: PatentFamily | None = None
        self._current_acquisition = None
        self.technology_classifier = TechnologyClassifier()
        self.translation_settings_path = self.runtime.paths.root / "translation.json"
        self.translation_cache_path = self.runtime.paths.root / "translation-cache.json"
        self.translation_provider = UnconfiguredTranslationProvider()
        self._reload_translation_provider()
        self._search_technology_evidence: dict[str, tuple] = {}
        self._search_hits_by_number = {}
        self._reader_hit = None
        self._reader_document: PatentReaderDocument | None = None
        self._reader_figure_cache: dict[str, bytes] = {}
        self._reader_figure_original = None
        self._reader_figure_photo = None
        self._reader_figure_loading_url: str | None = None
        self._reader_figure_zoom_level = 0

        self.title("Patent Intelligence Workbench")
        self.geometry("1460x900")
        self.minsize(1180, 720)
        self.configure(bg="#F5F7FA")
        self.protocol("WM_DELETE_WINDOW", self._on_close)

        self._configure_style()
        self._build_shell()
        self.refresh_library()
        self.refresh_watch()

    def _configure_style(self) -> None:
        style = ttk.Style(self)
        if "clam" in style.theme_names():
            style.theme_use("clam")

        bg = "#F7FAFD"
        surface = "#FFFFFF"
        border = "#D9E2EC"
        text = "#16324F"
        muted = "#6B7F95"
        accent = "#1261D6"
        accent_hover = "#0D52BA"
        selected = "#E8F2FF"

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
            background="#EAF0F5",
            foreground="#52677B",
            padding=(12, 7),
            font=("Segoe UI", 9),
        )
        style.configure(
            "MetricValue.TLabel",
            background=surface,
            foreground=text,
            font=("Segoe UI Semibold", 20),
        )
        style.configure(
            "MetricLabel.TLabel",
            background=surface,
            foreground=muted,
            font=("Segoe UI", 9),
        )
        style.configure(
            "BadgeOn.TLabel",
            background="#DCFCE7",
            foreground="#166534",
            padding=(7, 3),
            font=("Segoe UI Semibold", 8),
        )
        style.configure(
            "BadgeOff.TLabel",
            background="#F3F4F6",
            foreground="#6B7280",
            padding=(7, 3),
            font=("Segoe UI Semibold", 8),
        )
        style.configure(
            "TButton",
            background="#E7EDF3",
            foreground="#34495E",
            borderwidth=1,
            bordercolor="#D2DAE3",
            lightcolor="#D2DAE3",
            darkcolor="#D2DAE3",
            font=("Segoe UI Semibold", 9),
            padding=(12, 7),
            relief="flat",
        )
        style.map(
            "TButton",
            background=[("active", "#DCE6EF"), ("pressed", "#D1DEE9"), ("disabled", "#F0F3F6")],
            foreground=[("active", "#1769AA"), ("disabled", "#9AA7B4")],
        )
        style.configure(
            "Accent.TButton",
            background=accent,
            foreground="#FFFFFF",
            borderwidth=0,
            padding=(14, 8),
        )
        style.map(
            "Accent.TButton",
            background=[
                ("active", accent_hover),
                ("pressed", "#0F4E82"),
                ("disabled", "#AFC4D6"),
            ],
            foreground=[("disabled", "#F7FAFC")],
        )
        style.configure(
            "Ghost.TButton",
            background="#FFFFFF",
            foreground="#52677B",
            borderwidth=1,
            bordercolor="#CDD7E1",
            lightcolor="#CDD7E1",
            darkcolor="#CDD7E1",
            relief="solid",
            padding=(12, 7),
        )
        style.configure(
            "Quiet.TButton",
            background="#FFFFFF",
            foreground="#66788A",
            borderwidth=0,
            relief="flat",
            padding=(9, 6),
            font=("Segoe UI", 9),
        )
        style.map(
            "Quiet.TButton",
            background=[("active", "#F2F6F9"), ("pressed", "#E8EFF5")],
            foreground=[("active", "#1769AA")],
        )
        style.map(
            "Ghost.TButton",
            background=[("active", "#F2F6F9"), ("pressed", "#E8EFF5")],
            foreground=[("active", "#1769AA")],
        )
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
            background="#1261D6",
            foreground="#EAF3FF",
            borderwidth=0,
            anchor="w",
            padding=(14, 11),
            font=("Segoe UI Semibold", 9),
        )
        style.map(
            "Nav.TButton",
            background=[("active", "#2470D9")],
            foreground=[("active", "#FFFFFF")],
        )
        style.configure(
            "NavActive.TButton",
            background="#0B56C4",
            foreground="#FFFFFF",
            borderwidth=0,
            anchor="w",
            padding=(14, 11),
            font=("Segoe UI Semibold", 9),
        )
        style.map(
            "NavActive.TButton",
            background=[("active", "#0A4FAF")],
            foreground=[("active", "#FFFFFF")],
        )
        style.configure(
            "Horizontal.TProgressbar",
            troughcolor="#E5E7EB",
            background="#1769AA",
            bordercolor="#DDE3EA",
            lightcolor="#1769AA",
            darkcolor="#1769AA",
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

        workspace = tk.Frame(self, bg="#F7FAFD")
        workspace.pack(fill="both", expand=True, padx=(0, 18), pady=(0, 12))

        sidebar = tk.Frame(workspace, bg="#1261D6", width=220, highlightthickness=0)
        sidebar.pack(side="left", fill="y")
        sidebar.pack_propagate(False)
        tk.Label(
            sidebar,
            text="PIW",
            bg="#1261D6",
            fg="#FFFFFF",
            font=("Segoe UI Semibold", 18),
            anchor="w",
            padx=14,
            pady=0,
        ).pack(fill="x", pady=(16, 0))
        tk.Label(
            sidebar,
            text="Patent Intelligence",
            bg="#1261D6",
            fg="#BFD8FF",
            font=("Segoe UI", 8),
            anchor="w",
            padx=14,
            pady=0,
        ).pack(fill="x", pady=(0, 16))
        tk.Label(
            sidebar,
            text="WORKSPACE",
            bg="#1261D6",
            fg="#9FC5FA",
            font=("Segoe UI Semibold", 8),
            anchor="w",
            padx=14,
            pady=0,
        ).pack(fill="x", pady=(0, 8))

        content = ttk.Frame(workspace)
        content.pack(side="left", fill="both", expand=True, padx=(22, 0))

        self.search_tab = ttk.Frame(content, padding=14)
        self.reader_tab = ttk.Frame(content, padding=14)
        self.family_tab = ttk.Frame(content, padding=14)
        self.watch_tab = ttk.Frame(content, padding=14)
        self.library_tab = ttk.Frame(content, padding=14)
        self.technology_tab = ttk.Frame(content, padding=14)
        self.evidence_tab = ttk.Frame(content, padding=14)
        self.settings_tab = ttk.Frame(content, padding=14)
        self._pages = {
            "search": self.search_tab,
            "reader": self.reader_tab,
            "family": self.family_tab,
            "watch": self.watch_tab,
            "library": self.library_tab,
            "technology": self.technology_tab,
            "evidence": self.evidence_tab,
            "settings": self.settings_tab,
        }
        self._nav_buttons = {}
        for key, label in (
            ("search", "⌕   Search"),
            ("reader", "▣   Patent Reader"),
            ("family", "◫   Patent Family"),
            ("watch", "◉   Patent Watch"),
            ("library", "▤   Local Library"),
            ("technology", "⌘   Technology"),
            ("evidence", "◇   Evidence"),
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
        self._build_reader_tab()
        self._build_family_tab()
        self._build_watch_tab()
        self._build_library_tab()
        self._build_technology_tab()
        self._build_evidence_tab()
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
        if page == "evidence" and hasattr(self, "evidence_tree"):
            self.refresh_evidence()

    def _build_search_tab(self) -> None:
        ttk.Label(self.search_tab, text="Patent Search", style="PageTitle.TLabel").pack(anchor="w")
        ttk.Label(
            self.search_tab,
            text="按专利号、公司、技术主题或公开网页进行检索与采集",
            style="Subtle.TLabel",
        ).pack(anchor="w", pady=(2, 10))

        metrics = ttk.Frame(self.search_tab)
        metrics.pack(fill="x", pady=(0, 10))
        self.dashboard_patents_var = tk.StringVar(value="0")
        self.dashboard_families_var = tk.StringVar(value="0")
        self.dashboard_watch_var = tk.StringVar(value="0")
        self.dashboard_evidence_var = tk.StringVar(value="0")
        for index, (label, variable, target) in enumerate(
            (
                ("Local patents", self.dashboard_patents_var, "library"),
                ("Patent families", self.dashboard_families_var, "family"),
                ("Watch rules", self.dashboard_watch_var, "watch"),
                ("Evidence", self.dashboard_evidence_var, "evidence"),
            )
        ):
            card = ttk.Frame(metrics, style="Surface.TFrame", padding=(14, 10))
            card.grid(row=0, column=index, sticky="ew", padx=(0, 8 if index < 3 else 0))
            value_label = ttk.Label(card, textvariable=variable, style="MetricValue.TLabel")
            value_label.pack(anchor="w")
            caption = ttk.Label(card, text=f"{label}  →", style="MetricLabel.TLabel")
            caption.pack(anchor="w")
            for widget in (card, value_label, caption):
                widget.bind("<Button-1>", lambda _event, page=target: self._show_page(page))
                widget.configure(cursor="hand2")
            metrics.columnconfigure(index, weight=1)

        search_card = ttk.LabelFrame(self.search_tab, text="检索条件", padding=12)
        search_card.pack(fill="x", pady=(0, 10))
        form = ttk.Frame(search_card, style="Surface.TFrame")
        form.pack(fill="x")

        ttk.Label(form, text="检索").grid(row=0, column=0, sticky="w")
        self.search_query_var = tk.StringVar(value="输入专利号、关键词或公司名称")
        query_entry = ttk.Entry(form, textvariable=self.search_query_var, width=52)
        query_entry.grid(row=1, column=0, padx=(0, 8), sticky="ew")
        query_entry.bind("<FocusIn>", self._clear_search_placeholder)
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

        results_card = ttk.LabelFrame(self.search_tab, text="检索结果", padding=8)
        results_card.pack(fill="both", expand=True, pady=(0, 8))

        results_toolbar = ttk.Frame(results_card, style="Surface.TFrame")
        results_toolbar.pack(fill="x", pady=(0, 7))
        self.search_result_count_var = tk.StringVar(value="尚未检索")
        ttk.Label(
            results_toolbar,
            textvariable=self.search_result_count_var,
            style="SurfaceSubtle.TLabel",
        ).pack(side="left")
        ttk.Label(
            results_toolbar,
            text="双击结果可直接进入 Patent Family",
            style="SurfaceSubtle.TLabel",
        ).pack(side="right")

        columns = ("number", "country", "title", "technology", "applicant", "date")
        self.search_tree = ttk.Treeview(
            results_card,
            columns=columns,
            show="headings",
            selectmode="browse",
        )
        headings = {
            "number": "公开号",
            "country": "国家",
            "title": "标题",
            "technology": "技术标签",
            "applicant": "申请人",
            "date": "公开日",
        }
        widths = {
            "number": 170,
            "country": 70,
            "title": 340,
            "technology": 360,
            "applicant": 210,
            "date": 100,
        }
        for column in columns:
            self.search_tree.heading(column, text=headings[column])
            self.search_tree.column(column, width=widths[column], anchor="w")
        self.search_tree.pack(fill="both", expand=True)
        self.search_tree.bind("<Double-1>", self._open_selected_in_reader)
        self.search_tree.bind("<<TreeviewSelect>>", self._render_search_technology_evidence)
        self.search_technology_var = tk.StringVar(
            value="Technology evidence: 选择检索结果查看自动分类证据"
        )
        ttk.Label(
            results_card,
            textvariable=self.search_technology_var,
            style="SurfaceSubtle.TLabel",
            wraplength=1160,
            justify="left",
        ).pack(fill="x", pady=(7, 0))

        evidence_card = ttk.LabelFrame(self.search_tab, text="Evidence 采集", padding=8)
        evidence_card.pack(fill="x", pady=(0, 2))
        actions = ttk.Frame(evidence_card, style="Surface.TFrame")
        actions.pack(fill="x")
        ttk.Button(
            actions,
            text="预览 / 翻译",
            command=self._open_selected_in_reader,
            style="Accent.TButton",
        ).pack(side="left")
        ttk.Button(
            actions,
            text="分析选中专利族",
            command=self._search_to_family,
            style="Ghost.TButton",
        ).pack(side="left", padx=(6, 0))
        ttk.Button(
            actions,
            text="采集 URL / 文件",
            command=self.acquire_source,
            style="Quiet.TButton",
        ).pack(side="left", padx=(6, 0))
        ttk.Button(
            actions,
            text="选择本地文件",
            command=self.choose_acquisition_file,
            style="Quiet.TButton",
        ).pack(side="left", padx=(2, 0))
        ttk.Button(
            actions,
            text="保存为证据",
            command=self.save_current_acquisition,
            style="Quiet.TButton",
        ).pack(side="left", padx=(2, 0))

        ttk.Label(
            actions,
            text="关联专利",
            style="SurfaceSubtle.TLabel",
        ).pack(side="left", padx=(16, 5))
        self.acquisition_link_var = tk.StringVar()
        ttk.Entry(
            actions,
            textvariable=self.acquisition_link_var,
            width=24,
        ).pack(side="left")

        self.acquisition_preview = tk.Text(
            evidence_card,
            height=6,
            wrap="word",
            borderwidth=0,
            highlightthickness=1,
            highlightbackground="#DDE3EA",
            background="#F9FBFC",
            foreground="#52677B",
            font=("Segoe UI", 9),
            padx=10,
            pady=8,
        )
        self.acquisition_preview.pack(fill="x", pady=(8, 0))
        self.acquisition_preview.insert("1.0", "采集结果将在这里显示 Markdown 预览。")
        self.acquisition_preview.configure(state="disabled")

    def _build_reader_tab(self) -> None:
        ttk.Label(self.reader_tab, text="Patent Reader", style="PageTitle.TLabel").pack(anchor="w")
        ttk.Label(
            self.reader_tab,
            text="专利预览、原文访问与中英对照翻译",
            style="Subtle.TLabel",
        ).pack(anchor="w", pady=(2, 10))
        header = ttk.LabelFrame(self.reader_tab, text="专利信息", padding=10)
        header.pack(fill="x", pady=(0, 10))
        self.reader_number_var = tk.StringVar(value="尚未选择专利")
        self.reader_title_var = tk.StringVar(value="")
        self.reader_classification_var = tk.StringVar(value="CPC/IPC —")
        ttk.Label(
            header,
            textvariable=self.reader_number_var,
            style="Surface.TLabel",
        ).pack(anchor="w")
        ttk.Label(
            header,
            textvariable=self.reader_title_var,
            wraplength=1000,
            style="SurfaceSubtle.TLabel",
        ).pack(anchor="w", pady=(4, 0))
        ttk.Label(header, textvariable=self.reader_classification_var).pack(anchor="w", pady=(4, 0))
        actions = ttk.Frame(header, style="Surface.TFrame")
        actions.pack(fill="x", pady=(8, 0))
        ttk.Button(
            actions,
            text="打开 Google Patents 原文",
            command=self.open_reader_source,
        ).pack(side="left")
        ttk.Button(
            actions,
            text="打开 / 下载 PDF",
            command=self.open_reader_pdf,
        ).pack(side="left", padx=(6, 0))
        self.reader_section_var = tk.StringVar(value="摘要")
        self.reader_section_box = ttk.Combobox(
            actions,
            textvariable=self.reader_section_var,
            values=("摘要", "权利要求", "说明书", "附图"),
            state="readonly",
            width=10,
        )
        self.reader_section_box.pack(side="left", padx=(6, 0))
        self.reader_section_box.bind(
            "<<ComboboxSelected>>",
            lambda _event: self._render_reader_section(),
        )
        ttk.Button(
            actions,
            text="翻译当前章节",
            command=self.translate_reader_section,
        ).pack(side="left", padx=(6, 0))
        ttk.Button(
            actions,
            text="翻译选中文本",
            command=self.translate_reader_selection,
        ).pack(side="left", padx=(6, 0))
        ttk.Button(actions, text="上一张", command=self.reader_previous_figure).pack(
            side="left", padx=(12, 0)
        )
        ttk.Button(actions, text="下一张", command=self.reader_next_figure).pack(
            side="left", padx=(4, 0)
        )
        ttk.Button(actions, text="打开原图", command=self.open_reader_figure).pack(
            side="left", padx=(4, 0)
        )
        ttk.Button(actions, text="适配", command=self.fit_reader_figure).pack(
            side="left", padx=(8, 0)
        )
        ttk.Button(actions, text="−", command=self.zoom_out_reader_figure).pack(
            side="left", padx=(4, 0)
        )
        ttk.Button(actions, text="+", command=self.zoom_in_reader_figure).pack(
            side="left", padx=(4, 0)
        )
        self.reader_figure_index = 0
        body = ttk.Panedwindow(self.reader_tab, orient="horizontal")
        body.pack(fill="both", expand=True)
        left = ttk.LabelFrame(body, text="原文 / 预览", padding=8)
        right = ttk.LabelFrame(body, text="中文译文", padding=8)
        body.add(left, weight=1)
        body.add(right, weight=1)
        self.reader_source_text = tk.Text(
            left,
            wrap="word",
            padx=18,
            pady=14,
            background="#FFFFFF",
            foreground="#243447",
            insertbackground="#243447",
            selectbackground="#DCEBFA",
            selectforeground="#172B3A",
            relief="flat",
            borderwidth=0,
            font=("Cambria", 11),
            spacing1=2,
            spacing2=1,
            spacing3=7,
        )
        self.reader_source_text.pack(fill="both", expand=True)

        self.reader_figure_frame = ttk.Frame(left)
        self.reader_figure_info_var = tk.StringVar(value="附图尚未加载")
        ttk.Label(
            self.reader_figure_frame,
            textvariable=self.reader_figure_info_var,
            style="Subtle.TLabel",
        ).pack(fill="x", pady=(0, 6))
        figure_canvas_wrap = ttk.Frame(self.reader_figure_frame)
        figure_canvas_wrap.pack(fill="both", expand=True)
        self.reader_figure_canvas = tk.Canvas(
            figure_canvas_wrap,
            background="#FFFFFF",
            highlightthickness=1,
            highlightbackground="#DDE3EA",
        )
        figure_vscroll = ttk.Scrollbar(
            figure_canvas_wrap,
            orient="vertical",
            command=self.reader_figure_canvas.yview,
        )
        figure_hscroll = ttk.Scrollbar(
            figure_canvas_wrap,
            orient="horizontal",
            command=self.reader_figure_canvas.xview,
        )
        self.reader_figure_canvas.configure(
            yscrollcommand=figure_vscroll.set,
            xscrollcommand=figure_hscroll.set,
        )
        self.reader_figure_canvas.grid(row=0, column=0, sticky="nsew")
        figure_vscroll.grid(row=0, column=1, sticky="ns")
        figure_hscroll.grid(row=1, column=0, sticky="ew")
        figure_canvas_wrap.rowconfigure(0, weight=1)
        figure_canvas_wrap.columnconfigure(0, weight=1)
        self.reader_figure_canvas.bind(
            "<Double-1>",
            lambda _event: self.open_reader_figure(),
        )
        self.reader_figure_canvas.bind("<Configure>", self._on_reader_figure_resize)

        self.reader_translation_text = tk.Text(right, wrap="word", padx=10, pady=8)
        self.reader_translation_text.pack(fill="both", expand=True)
        self.reader_translation_text.insert("1.0", "译文将在这里显示。")
        self.reader_translation_text.configure(state="disabled")

    def _open_selected_in_reader(self, _event=None) -> None:
        selection = self.search_tree.selection()
        if not selection:
            return
        hit = self._search_hits_by_number.get(selection[0])
        if hit is None:
            return
        self._reader_hit = hit
        self._reader_document = PatentReaderDocument(
            publication_number=hit.publication_number,
            title=hit.title,
            abstract=hit.abstract,
            classifications=hit.classifications,
        )
        self.reader_figure_index = 0
        self._reader_figure_loading_url = None
        self._reader_figure_original = None
        self._reader_figure_photo = None
        self._reader_figure_zoom_level = 0
        self.reader_section_var.set("摘要")
        self._show_reader_text_view()
        self.reader_number_var.set(hit.publication_number)
        self.reader_title_var.set(hit.title or "")
        classes = ", ".join(hit.classifications) or "—"
        self.reader_classification_var.set(f"CPC/IPC {classes}")
        source = []
        if hit.title:
            source.append(hit.title)
        if hit.abstract:
            source.append("\nABSTRACT\n" + hit.abstract)
        if hit.classifications:
            source.append("\nCLASSIFICATIONS\n" + ", ".join(hit.classifications))
        self.reader_source_text.delete("1.0", "end")
        self.reader_source_text.insert("1.0", "\n".join(source) or "暂无结构化预览内容。")
        self._set_reader_translation("")
        self._show_page("reader")
        self._load_reader_document()

    def _load_reader_document(self) -> None:
        if self._reader_hit is None:
            return
        try:
            publication = normalize_patent_number(self._reader_hit.publication_number)
        except PatentNumberError:
            return
        provider = GooglePatentsSearchProvider()

        async def task():
            return await provider.get_reader_document(publication)

        run_async_in_thread(
            task,
            on_success=self._on_reader_document_loaded,
            on_error=lambda exc: self._set_status(f"Reader 全文加载失败：{exc}"),
            schedule_ui=self._ui_callbacks.submit,
        )

    def _on_reader_document_loaded(self, document: PatentReaderDocument) -> None:
        self._reader_document = document
        self._render_reader_section()
        self._set_status(f"Reader 全文已加载：{document.publication_number}")

    def _show_reader_text_view(self) -> None:
        self.reader_figure_frame.pack_forget()
        if not self.reader_source_text.winfo_ismapped():
            self.reader_source_text.pack(fill="both", expand=True)

    def _show_reader_figure_view(self) -> None:
        self.reader_source_text.pack_forget()
        if not self.reader_figure_frame.winfo_ismapped():
            self.reader_figure_frame.pack(fill="both", expand=True)

    def _render_reader_section(self) -> None:
        document = self._reader_document
        if document is None:
            return
        section = self.reader_section_var.get()
        if section == "附图":
            self._render_reader_figure()
            return
        self._show_reader_text_view()
        text = {
            "摘要": document.abstract or "暂无摘要。",
            "权利要求": document.claims or "暂无权利要求文本。",
            "说明书": document.description or "暂无说明书文本。",
        }.get(section, document.abstract or "")
        self.reader_source_text.delete("1.0", "end")
        self.reader_source_text.insert("1.0", text)

    def _render_reader_figure(self) -> None:
        self._show_reader_figure_view()
        document = self._reader_document
        if document is None or not document.figures:
            self.reader_figure_info_var.set("暂无附图。")
            self.reader_figure_canvas.delete("all")
            return
        self.reader_figure_index %= len(document.figures)
        figure = document.figures[self.reader_figure_index]
        self.reader_figure_info_var.set(
            f"Figure {self.reader_figure_index + 1}/{len(document.figures)} · 正在加载…"
        )
        self._load_reader_figure_image(figure.full_url)

    def _load_reader_figure_image(self, url: str) -> None:
        self._reader_figure_loading_url = url
        cached = self._reader_figure_cache.get(url)
        if cached is not None:
            self._on_reader_figure_image_loaded(url, cached)
            return

        async def task():
            async with httpx.AsyncClient(timeout=30.0, follow_redirects=True) as client:
                response = await client.get(url)
                response.raise_for_status()
                return response.content

        run_async_in_thread(
            task,
            on_success=lambda data, image_url=url: self._on_reader_figure_image_loaded(
                image_url,
                data,
            ),
            on_error=lambda exc: self._on_reader_figure_image_error(url, exc),
            schedule_ui=self._ui_callbacks.submit,
        )

    def _on_reader_figure_image_loaded(self, url: str, data: bytes) -> None:
        if url != self._reader_figure_loading_url:
            return
        self._reader_figure_cache[url] = data
        try:
            encoded = base64.b64encode(data).decode("ascii")
            self._reader_figure_original = tk.PhotoImage(data=encoded)
        except tk.TclError as exc:
            self._on_reader_figure_image_error(url, exc)
            return
        self._reader_figure_zoom_level = 0
        self._display_reader_figure_image()
        document = self._reader_document
        total = len(document.figures) if document else 0
        self.reader_figure_info_var.set(
            f"Figure {self.reader_figure_index + 1}/{total} · 双击图片打开原图"
        )

    def _on_reader_figure_image_error(self, url: str, exc: Exception) -> None:
        if url != self._reader_figure_loading_url:
            return
        self.reader_figure_canvas.delete("all")
        self.reader_figure_info_var.set(f"附图加载失败：{exc}")

    def _display_reader_figure_image(self) -> None:
        original = self._reader_figure_original
        if original is None:
            return
        canvas = self.reader_figure_canvas
        viewport_width = max(canvas.winfo_width() - 20, 100)
        viewport_height = max(canvas.winfo_height() - 20, 100)
        scale = figure_scale(
            original.width(),
            original.height(),
            viewport_width,
            viewport_height,
            self._reader_figure_zoom_level,
        )
        photo = original
        if scale.subsample > 1:
            photo = photo.subsample(scale.subsample, scale.subsample)
        if scale.zoom > 1:
            photo = photo.zoom(scale.zoom, scale.zoom)
        self._reader_figure_photo = photo
        canvas.delete("all")
        width = max(viewport_width, photo.width())
        height = max(viewport_height, photo.height())
        x = max((viewport_width - photo.width()) // 2, 0)
        y = max((viewport_height - photo.height()) // 2, 0)
        canvas.create_image(x, y, image=photo, anchor="nw")
        canvas.configure(scrollregion=(0, 0, width, height))

    def _on_reader_figure_resize(self, _event=None) -> None:
        if self._reader_figure_zoom_level == 0:
            self._display_reader_figure_image()

    def fit_reader_figure(self) -> None:
        self._reader_figure_zoom_level = 0
        self._display_reader_figure_image()

    def zoom_in_reader_figure(self) -> None:
        self._reader_figure_zoom_level = min(4, self._reader_figure_zoom_level + 1)
        self._display_reader_figure_image()

    def zoom_out_reader_figure(self) -> None:
        self._reader_figure_zoom_level = max(-6, self._reader_figure_zoom_level - 1)
        self._display_reader_figure_image()

    def reader_previous_figure(self) -> None:
        document = self._reader_document
        if document is None or not document.figures:
            return
        self.reader_figure_index = (self.reader_figure_index - 1) % len(document.figures)
        self._reader_figure_zoom_level = 0
        self.reader_section_var.set("附图")
        self._render_reader_figure()

    def reader_next_figure(self) -> None:
        document = self._reader_document
        if document is None or not document.figures:
            return
        self.reader_figure_index = (self.reader_figure_index + 1) % len(document.figures)
        self._reader_figure_zoom_level = 0
        self.reader_section_var.set("附图")
        self._render_reader_figure()

    def open_reader_figure(self) -> None:
        document = self._reader_document
        if document is None or not document.figures:
            return
        self.reader_figure_index %= len(document.figures)
        webbrowser.open(document.figures[self.reader_figure_index].full_url)

    def _set_reader_translation(self, text: str) -> None:
        self.reader_translation_text.configure(state="normal")
        self.reader_translation_text.delete("1.0", "end")
        self.reader_translation_text.insert("1.0", text or "译文将在这里显示。")
        self.reader_translation_text.configure(state="disabled")
    def open_reader_source(self) -> None:
        if self._reader_hit is None:
            return
        url = f"https://patents.google.com/patent/{self._reader_hit.publication_number}/en"
        webbrowser.open(url)

    def open_reader_pdf(self) -> None:
        hit = self._reader_hit
        if hit is None:
            return
        try:
            publication = normalize_patent_number(hit.publication_number)
        except PatentNumberError as exc:
            self._set_status(f"PDF 下载失败：{exc}")
            return

        local_pdf = self._find_reader_library_pdf(publication.canonical)
        if local_pdf is not None:
            self._ensure_reader_pdf_registered(hit, local_pdf)
            open_local_path(local_pdf)
            self._set_status(f"已从专利库打开 PDF：{local_pdf}")
            return

        company_name = self._reader_company_folder_name(hit.applicants)
        destination = patent_archive_path(
            self.runtime.library_root,
            company_name,
            publication.canonical,
            hit.title,
        )
        self._set_status(f"专利库未找到 PDF，开始下载：{publication.canonical}")

        async def task():
            return await self.runtime.family_downloader.manager.download(
                publication,
                destination,
            )

        run_async_in_thread(
            task,
            on_success=lambda result, current_hit=hit: self._on_reader_pdf_ready(
                result,
                current_hit,
            ),
            on_error=lambda exc: self._set_status(f"PDF 下载失败：{exc}"),
            schedule_ui=self._ui_callbacks.submit,
        )

    def _find_reader_library_pdf(self, publication_number: str):
        patent = self.runtime.library_store.get_patent(publication_number)
        if patent is not None:
            for document in patent.documents:
                if document.path.is_file():
                    return document.path

        pattern = f"*{publication_number}*.pdf"
        for path in self.runtime.library_root.rglob(pattern):
            if path.is_file():
                return path
        return None

    def _reader_company_folder_name(self, applicants: tuple[str, ...]) -> str:
        registry = (
            self.runtime.search_service.company_registry
            if self.runtime.search_service
            else None
        )
        if registry is not None:
            for name in applicants:
                try:
                    return registry.get(name).display_name
                except KeyError:
                    continue
        return applicants[0] if applicants else "待归类"

    def _ensure_reader_pdf_registered(
        self,
        hit,
        path,
        *,
        provider: str | None = None,
        source_url: str | None = None,
    ) -> None:
        publication = normalize_patent_number(hit.publication_number)
        if self.runtime.library_store.get_patent(publication.canonical) is None:
            self.runtime.library_store.upsert_publication(
                PatentPublication(
                    publication_number=publication.canonical,
                    jurisdiction=publication.jurisdiction,
                    kind_code=publication.kind_code,
                    title=hit.title,
                    publication_date=hit.publication_date,
                    original_assignees=hit.applicants,
                ),
                source=provider or "READER_LIBRARY",
            )
        self.runtime.library_store.attach_pdf(
            publication.canonical,
            path,
            provider=provider or "LOCAL_LIBRARY",
            source_url=source_url,
        )

    def _on_reader_pdf_ready(self, result, hit) -> None:
        self._ensure_reader_pdf_registered(
            hit,
            result.path,
            provider=result.provider,
            source_url=result.source_url,
        )
        open_local_path(result.path)
        self.refresh_library()
        self._set_status(f"PDF 已归档到专利库并打开：{result.path}")

    def _translate_reader_text(self, text: str) -> None:
        if not text.strip():
            self._set_reader_translation("没有可翻译的文本。")
            return
        self._set_reader_translation("正在翻译…")

        def task():
            return self.translation_provider.translate(text)

        run_async_in_thread(
            task,
            on_success=lambda result: self._set_reader_translation(result.text),
            on_error=lambda exc: self._set_reader_translation(str(exc)),
            schedule_ui=self._ui_callbacks.submit,
        )

    def translate_reader_section(self) -> None:
        if self.reader_section_var.get() == "附图":
            self._set_reader_translation("附图章节不进行文本翻译；可双击图片打开原图。")
            return
        text = self.reader_source_text.get("1.0", "end").strip()
        self._translate_reader_text(text)

    def translate_reader_selection(self) -> None:
        try:
            text = self.reader_source_text.get("sel.first", "sel.last")
        except tk.TclError:
            self._set_reader_translation("请先在左侧选择要翻译的文本。")
            return
        self._translate_reader_text(text)

    def translate_reader_abstract(self) -> None:
        self.reader_section_var.set("摘要")
        self._render_reader_section()
        self.translate_reader_section()

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
            style="Ghost.TButton",
        ).grid(row=1, column=3, padx=(0, 8))
        self.family_download_button = ttk.Button(
            form,
            text="下载全部专利 PDF",
            command=self.download_current_family,
            style="Ghost.TButton",
        )
        self.family_download_button.grid(row=1, column=4)

        columns = ("number", "country", "title", "application", "date")
        family_results = ttk.LabelFrame(self.family_tab, text="Family 成员", padding=8)
        family_results.pack(fill="both", expand=True, pady=(0, 8))
        self.family_tree = ttk.Treeview(
            family_results,
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
        self.family_country_var = tk.StringVar(value="Jurisdictions  —")
        ttk.Label(
            family_summary_card,
            textvariable=self.family_country_var,
            style="Surface.TLabel",
        ).pack(fill="x", pady=(5, 0))

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
        watch_summary = ttk.Frame(self.watch_tab, style="Surface.TFrame", padding=(12, 8))
        watch_summary.pack(fill="x", pady=(0, 10))
        self.watch_summary_var = tk.StringVar(
            value="Enabled 0   ·   Disabled 0   ·   Recent runs 0"
        )
        ttk.Label(
            watch_summary,
            textvariable=self.watch_summary_var,
            style="SurfaceSubtle.TLabel",
        ).pack(anchor="w")
        watch_toolbar_card = ttk.LabelFrame(self.watch_tab, text="监控控制", padding=10)
        watch_toolbar_card.pack(fill="x", pady=(0, 10))
        toolbar = ttk.Frame(watch_toolbar_card, style="Surface.TFrame")
        toolbar.pack(fill="x")
        ttk.Button(
            toolbar,
            text="刷新",
            command=self.refresh_watch,
            style="Quiet.TButton",
        ).pack(side="left")
        ttk.Button(
            toolbar,
            text="切换启用状态",
            command=self.toggle_selected_watch_rule,
            style="Ghost.TButton",
        ).pack(side="left", padx=(6, 0))
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
            style="Ghost.TButton",
        ).pack(side="left", padx=(6, 0))

        rules_card = ttk.LabelFrame(self.watch_tab, text="监控规则", padding=8)
        rules_card.pack(fill="both", expand=True, pady=(0, 8))
        self.watch_rule_tree = ttk.Treeview(
            rules_card,
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

        history_card = ttk.LabelFrame(self.watch_tab, text="最近运行", padding=8)
        history_card.pack(fill="both", expand=True)
        self.watch_history_tree = ttk.Treeview(
            history_card,
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

        library_root = self.runtime.library_root or self.runtime.paths.downloads
        self.library_root_var = tk.StringVar(value=str(library_root))
        ttk.Label(toolbar, text="专利库目录").pack(side="left")
        ttk.Entry(
            toolbar,
            textvariable=self.library_root_var,
            width=42,
        ).pack(side="left", padx=(5, 4))
        ttk.Button(
            toolbar,
            text="选择目录",
            command=self.choose_library_root,
            style="Quiet.TButton",
        ).pack(side="left", padx=(0, 8))

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
            style="Accent.TButton",
        ).pack(side="left", padx=(8, 0))
        ttk.Button(
            toolbar,
            text="导出 CSV",
            command=lambda: self.export_library(".csv"),
            style="Quiet.TButton",
        ).pack(side="left", padx=(6, 0))
        ttk.Button(
            toolbar,
            text="导出 Excel",
            command=lambda: self.export_library(".xlsx"),
            style="Ghost.TButton",
        ).pack(side="left", padx=(2, 0))
        self.library_enrich_button = ttk.Button(
            toolbar,
            text="补全元数据",
            command=self.enrich_library_metadata,
            style="Quiet.TButton",
        )
        self.library_enrich_button.pack(side="left", padx=(6, 0))
        self.library_enrich_status_var = tk.StringVar(value="元数据补全：未运行")
        ttk.Label(
            toolbar,
            textvariable=self.library_enrich_status_var,
            style="SurfaceSubtle.TLabel",
        ).pack(side="left", padx=(10, 0))

        library_results = ttk.LabelFrame(self.library_tab, text="专利库", padding=8)
        library_results.pack(fill="both", expand=True, pady=(0, 8))
        self.library_tree = ttk.Treeview(
            library_results,
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
        detail.pack(fill="x", pady=(0, 0))

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
            highlightbackground="#DDE3EA",
            selectbackground="#EAF3FB",
            selectforeground="#25364A",
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
            highlightbackground="#DDE3EA",
            background="#F9FBFC",
            foreground="#52677B",
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
            style="Ghost.TButton",
        ).pack(side="left", padx=(8, 0))
        ttk.Button(
            actions,
            text="打开所在目录",
            command=self.open_selected_library_folder,
            style="Quiet.TButton",
        ).pack(side="left", padx=(4, 0))

        detail.columnconfigure(1, weight=2)
        detail.columnconfigure(2, weight=1)
        detail.columnconfigure(4, weight=2)

    def _build_technology_tab(self) -> None:
        ttk.Label(
            self.technology_tab,
            text="Technology Taxonomy",
            style="PageTitle.TLabel",
        ).pack(anchor="w")
        ttk.Label(
            self.technology_tab,
            text="悬架与减振器工程专利分类树",
            style="Subtle.TLabel",
        ).pack(anchor="w", pady=(2, 10))

        card = ttk.Frame(self.technology_tab, style="Surface.TFrame", padding=12)
        card.pack(fill="both", expand=True)
        self.technology_tree = ttk.Treeview(card, show="tree", selectmode="browse")
        self.technology_tree.pack(fill="both", expand=True)

        self.technology_taxonomy = TechnologyTaxonomy.default()

        def insert_nodes(parent: str, nodes) -> None:
            for node in nodes:
                item = self.technology_tree.insert(parent, "end", iid=node.node_id, text=node.name)
                insert_nodes(item, node.children)

        insert_nodes("", self.technology_taxonomy.roots)
        for node_id in ("suspension", "passive_damper"):
            if self.technology_tree.exists(node_id):
                self.technology_tree.item(node_id, open=True)
        self.technology_tree.bind("<<TreeviewSelect>>", self._on_technology_selected)
        self.technology_tree.bind("<Double-1>", self._search_selected_technology)
        ttk.Button(
            self.technology_tab,
            text="检索选中技术",
            command=self._search_selected_technology,
            style="Accent.TButton",
        ).pack(anchor="e", pady=(10, 0))

    def _on_technology_selected(self, _event=None) -> None:
        selection = self.technology_tree.selection()
        if not selection:
            return
        current = selection[0]
        path = []
        while current:
            path.append(self.technology_tree.item(current, "text"))
            current = self.technology_tree.parent(current)
        self._set_status("Technology: " + " > ".join(reversed(path)))

    def _search_selected_technology(self, _event=None) -> None:
        selection = self.technology_tree.selection()
        if not selection:
            return
        node = self.technology_taxonomy.find(selection[0])
        if not node.search_terms:
            self._set_status(f"Technology: {node.name} · 请选择可检索的叶节点")
            return
        self.search_query_var.set(" OR ".join(node.search_terms))
        self.search_scope_var.set("具体技术主题")
        self._show_page("search")
        self._set_status(f"已载入技术检索：{node.name}")

    def _build_evidence_tab(self) -> None:
        ttk.Label(self.evidence_tab, text="Evidence Center", style="PageTitle.TLabel").pack(
            anchor="w"
        )
        ttk.Label(
            self.evidence_tab,
            text="集中检索、浏览并追溯网页、PDF 与 Office 文档采集证据",
            style="Subtle.TLabel",
        ).pack(anchor="w", pady=(2, 10))

        toolbar_card = ttk.LabelFrame(self.evidence_tab, text="Evidence 检索", padding=10)
        toolbar_card.pack(fill="x", pady=(0, 10))
        toolbar = ttk.Frame(toolbar_card, style="Surface.TFrame")
        toolbar.pack(fill="x")
        self.evidence_query_var = tk.StringVar()
        entry = ttk.Entry(toolbar, textvariable=self.evidence_query_var, width=36)
        entry.pack(side="left", fill="x", expand=True)
        entry.bind("<Return>", lambda _event: self.refresh_evidence())
        self.evidence_type_var = tk.StringVar(value="All types")
        ttk.Combobox(
            toolbar,
            textvariable=self.evidence_type_var,
            values=("All types", "url", "file"),
            state="readonly",
            width=12,
        ).pack(side="left", padx=(8, 0))
        self.evidence_company_var = tk.StringVar()
        ttk.Entry(
            toolbar,
            textvariable=self.evidence_company_var,
            width=16,
        ).pack(side="left", padx=(8, 0))
        self.evidence_topic_var = tk.StringVar()
        ttk.Entry(
            toolbar,
            textvariable=self.evidence_topic_var,
            width=16,
        ).pack(side="left", padx=(8, 0))
        ttk.Button(
            toolbar,
            text="搜索",
            command=self.refresh_evidence,
            style="Accent.TButton",
        ).pack(side="left", padx=(8, 0))

        evidence_summary = ttk.Frame(self.evidence_tab, style="Surface.TFrame", padding=(12, 8))
        evidence_summary.pack(fill="x", pady=(0, 8))
        self.evidence_summary_var = tk.StringVar(value="Evidence 0")
        ttk.Label(
            evidence_summary,
            textvariable=self.evidence_summary_var,
            style="SurfaceSubtle.TLabel",
        ).pack(side="left")

        pane = ttk.Panedwindow(self.evidence_tab, orient="horizontal")
        pane.pack(fill="both", expand=True)
        left = ttk.Frame(pane, style="Surface.TFrame", padding=8)
        right = ttk.Frame(pane, style="Surface.TFrame", padding=10)
        pane.add(left, weight=3)
        pane.add(right, weight=2)

        columns = ("type", "title", "patent", "company", "topic", "captured")
        self.evidence_tree = ttk.Treeview(left, columns=columns, show="headings")
        for column, title, width in (
            ("type", "类型", 80),
            ("title", "标题 / 来源", 300),
            ("patent", "关联专利", 130),
            ("company", "公司", 110),
            ("topic", "技术主题", 130),
            ("captured", "采集时间", 150),
        ):
            self.evidence_tree.heading(column, text=title)
            self.evidence_tree.column(column, width=width, anchor="w")
        self.evidence_tree.pack(fill="both", expand=True)
        self.evidence_tree.bind("<<TreeviewSelect>>", self._load_evidence_center_preview)

        self.evidence_preview = tk.Text(
            right,
            wrap="word",
            borderwidth=0,
            highlightthickness=1,
            highlightbackground="#E5E7EB",
            background="#F9FAFB",
            foreground="#374151",
            font=("Segoe UI", 9),
            padx=12,
            pady=10,
        )
        self.evidence_preview.pack(fill="both", expand=True)
        self.evidence_preview.configure(state="disabled")
        self._evidence_center_records = ()

    def refresh_evidence(self) -> None:
        query = self.evidence_query_var.get().strip() or None
        source_type = self.evidence_type_var.get()
        self._evidence_center_records = self.runtime.library_store.list_evidence(
            text=query,
            source_type=None if source_type == "All types" else source_type,
            company_group=self.evidence_company_var.get().strip() or None,
            technology_topic=self.evidence_topic_var.get().strip() or None,
            limit=1000,
        )
        self.evidence_tree.delete(*self.evidence_tree.get_children())
        for record in self._evidence_center_records:
            self.evidence_tree.insert(
                "",
                "end",
                iid=record.evidence_id,
                values=(
                    record.source_type,
                    record.title or record.source,
                    record.publication_number or "—",
                    record.company_group or "—",
                    record.technology_topic or "—",
                    record.captured_at.strftime("%Y-%m-%d %H:%M"),
                ),
            )
        self.evidence_preview.configure(state="normal")
        self.evidence_preview.delete("1.0", "end")
        if not self._evidence_center_records:
            self.evidence_preview.insert(
                "1.0",
                "No evidence found.\n\n从 Search 页面使用“采集 URL / 文件”创建第一条 Evidence。",
            )
        self.evidence_preview.configure(state="disabled")
        self.evidence_summary_var.set(f"Evidence {len(self._evidence_center_records)}")
        self._set_status(f"Evidence：{len(self._evidence_center_records)} 条")

    def _load_evidence_center_preview(self, _event=None) -> None:
        selection = self.evidence_tree.selection()
        if not selection:
            return
        evidence_id = selection[0]
        record = next(
            (item for item in self._evidence_center_records if item.evidence_id == evidence_id),
            None,
        )
        if record is None:
            return
        preview = (
            f"{record.title or 'Untitled Evidence'}\n\n"
            f"Source: {record.source}\n"
            f"Type: {record.source_type}\n"
            f"Patent: {record.publication_number or '—'}\n"
            f"Company: {record.company_group or '—'}\n"
            f"Topic: {record.technology_topic or '—'}\n"
            f"Captured: {record.captured_at.isoformat()}\n\n"
            f"{record.markdown[:12000]}"
        )
        self.evidence_preview.configure(state="normal")
        self.evidence_preview.delete("1.0", "end")
        self.evidence_preview.insert("1.0", preview)
        self.evidence_preview.configure(state="disabled")

    def _build_settings_tab(self) -> None:
        credentials = self.runtime.current_epo_credentials()
        translation = load_translation_settings(self.translation_settings_path)

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

        translation_frame = ttk.LabelFrame(
            self.settings_tab,
            text="Translation",
            padding=12,
        )
        translation_frame.pack(fill="x", pady=(12, 0))
        self.translation_endpoint_var = tk.StringVar(
            value=translation.endpoint if translation else ""
        )
        self.translation_api_key_var = tk.StringVar(
            value=translation.api_key if translation else ""
        )
        self.translation_status_var = tk.StringVar(
            value="翻译服务：已配置" if translation else "翻译服务：未配置"
        )
        ttk.Label(translation_frame, text="Endpoint").grid(row=0, column=0, sticky="w")
        ttk.Entry(
            translation_frame,
            textvariable=self.translation_endpoint_var,
            width=72,
        ).grid(row=1, column=0, padx=(0, 10), sticky="ew")
        ttk.Label(translation_frame, text="API Key（可选）").grid(row=0, column=1, sticky="w")
        ttk.Entry(
            translation_frame,
            textvariable=self.translation_api_key_var,
            show="●",
            width=42,
        ).grid(row=1, column=1, padx=(0, 10), sticky="ew")
        ttk.Button(
            translation_frame,
            text="保存翻译配置",
            command=self.save_translation_settings,
        ).grid(row=1, column=2, padx=(0, 8))
        ttk.Button(
            translation_frame,
            text="删除翻译配置",
            command=self.delete_translation_settings,
        ).grid(row=1, column=3)
        ttk.Label(
            translation_frame,
            textvariable=self.translation_status_var,
            style="Subtle.TLabel",
        ).grid(row=2, column=0, columnspan=4, sticky="w", pady=(10, 0))
        translation_frame.columnconfigure(0, weight=1)
        translation_frame.columnconfigure(1, weight=1)

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

    def _reload_translation_provider(self) -> None:
        settings = load_translation_settings(self.translation_settings_path)
        if settings is None:
            self.translation_provider = UnconfiguredTranslationProvider()
            return
        self.translation_provider = CachedTranslationProvider(
            provider=HttpTranslationProvider(
                endpoint=settings.endpoint,
                api_key=settings.api_key or None,
            ),
            cache_path=self.translation_cache_path,
        )

    def save_translation_settings(self) -> None:
        endpoint = self.translation_endpoint_var.get().strip()
        api_key = self.translation_api_key_var.get().strip()
        if not endpoint:
            messagebox.showinfo("缺少配置", "Translation Endpoint 必须填写。")
            return
        save_translation_settings(
            self.translation_settings_path,
            TranslationSettings(endpoint=endpoint, api_key=api_key),
        )
        self._reload_translation_provider()
        self.translation_status_var.set("翻译服务：已配置")
        self._set_status("翻译服务配置已保存")

    def delete_translation_settings(self) -> None:
        delete_translation_settings(self.translation_settings_path)
        self.translation_endpoint_var.set("")
        self.translation_api_key_var.set("")
        self._reload_translation_provider()
        self.translation_status_var.set("翻译服务：未配置")
        self._set_status("翻译服务配置已删除")

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
        else:
            self.library_evidence_preview.insert(
                "1.0",
                "No linked evidence yet.\n\n"
                "Use Search → 采集 URL / 文件，将网页、PDF 或 Office 文档"
                "采集为 Markdown Evidence，并关联到当前专利。",
            )
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

    def _clear_search_placeholder(self, _event=None) -> None:
        if self.search_query_var.get() == "输入专利号、关键词或公司名称":
            self.search_query_var.set("")

    def run_search(self) -> None:
        service = self.runtime.search_service
        if service is None:
            messagebox.showwarning("未配置", self.runtime.search_status)
            return

        query = self.search_query_var.get().strip()
        if query == "输入专利号、关键词或公司名称":
            query = ""
        company = self.search_company_var.get().strip() or None
        if company:
            try:
                company = service.company_registry.get(company).display_name
            except KeyError:
                messagebox.showerror(
                    "公司未识别",
                    "请输入公司下拉列表中的公司，或直接在检索框输入公司名称。",
                )
                return
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

    def _technology_display_labels(self, matches) -> tuple[str, ...]:
        labels: list[str] = []
        for match in matches:
            try:
                path = self.technology_classifier.taxonomy.path(match.node_id)
            except KeyError:
                path = ()
            if path:
                nodes = [node for node in path if node.node_id != "suspension"]
                names = [node.name for node in nodes]
            else:
                names = [match.name]
            for name in names:
                if name not in labels:
                    labels.append(name)
        return tuple(labels)

    def _render_search_response(self, response) -> None:
        self.search_button.state(["!disabled"])
        self.search_tree.delete(*self.search_tree.get_children())
        self._search_technology_evidence.clear()
        self._search_hits_by_number.clear()
        for hit in response.page.hits:
            self._search_hits_by_number[hit.publication_number] = hit
            classification_text = " ".join(
                part
                for part in (
                    hit.title or "",
                    hit.abstract or "",
                    " ".join(hit.applicants),
                )
                if part
            )
            matches = self.technology_classifier.classify(
                text=classification_text,
                classifications=hit.classifications,
            )
            self._search_technology_evidence[hit.publication_number] = matches
            tag_text = " / ".join(self._technology_display_labels(matches))
            self.search_tree.insert(
                "",
                "end",
                iid=hit.publication_number,
                values=(
                    hit.publication_number,
                    hit.jurisdiction,
                    hit.title or "",
                    tag_text,
                    ", ".join(hit.applicants),
                    hit.publication_date.isoformat() if hit.publication_date else "",
                ),
            )
        total = response.page.total_result_count
        shown = len(response.page.hits)
        self.search_result_count_var.set(
            f"{response.provider} · 显示 {shown} 条"
            + (f" / 共 {total} 条" if total is not None else "")
        )
        self._set_status(
            f"搜索完成：{response.provider} · 显示 {shown} 条"
            + (f" / 共 {total} 条" if total is not None else "")
        )

    def _render_search_technology_evidence(self, _event=None) -> None:
        selection = self.search_tree.selection()
        if not selection:
            self.search_technology_var.set(
                "Technology evidence: 选择检索结果查看自动分类证据"
            )
            return
        matches = self._search_technology_evidence.get(selection[0], ())
        if not matches:
            self.search_technology_var.set("Technology evidence: 暂无匹配标签")
            return
        hierarchy = " / ".join(self._technology_display_labels(matches))
        parts = []
        for match in matches:
            evidence = list(match.matched_terms) + list(match.matched_classifications)
            evidence_text = ", ".join(evidence) if evidence else "rule match"
            parts.append(f"{match.name} [{evidence_text}]")
        self.search_technology_var.set(
            "Technology: " + hierarchy + "    Evidence: " + " | ".join(parts)
        )

    def _search_to_family(self, _event=None) -> None:
        selection = self.search_tree.selection()
        if not selection:
            return
        self.family_number_var.set(selection[0])
        self._show_page("family")
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
        jurisdiction_counts: dict[str, int] = {}
        for member in family.members:
            jurisdiction_counts[member.jurisdiction] = (
                jurisdiction_counts.get(member.jurisdiction, 0) + 1
            )
        distribution = "   ".join(
            f"{code} {count}"
            for code, count in sorted(
                jurisdiction_counts.items(), key=lambda item: (-item[1], item[0])
            )
        )
        self.family_country_var.set(f"Jurisdictions  {distribution or '—'}")
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
            return self._download_family_to_library_root(
                family,
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

    def _download_family_to_library_root(self, family, *, on_progress=None):
        root = self.runtime.library_root or self.runtime.paths.downloads
        company_name = self._family_company_folder_name(family)
        company_root = root / company_name
        company_root.mkdir(parents=True, exist_ok=True)
        return self.runtime.family_downloader.download_family(
            family,
            company_root,
            on_progress=on_progress,
        )

    def _family_company_folder_name(self, family) -> str:
        registry = (
            self.runtime.search_service.company_registry
            if self.runtime.search_service
            else None
        )
        assignees = [
            name
            for member in family.members
            for name in (member.current_assignees or member.original_assignees)
        ]
        if registry is not None:
            for name in assignees:
                try:
                    return registry.get(name).display_name
                except KeyError:
                    continue
        return assignees[0] if assignees else "待归类"

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
        rules = self.runtime.watch_store.list_rules()
        recent_runs = self.runtime.watch_store.recent_runs(limit=30)
        enabled_count = sum(1 for rule in rules if rule.enabled)
        self.watch_summary_var.set(
            f"Enabled {enabled_count}   ·   Disabled {len(rules) - enabled_count}"
            f"   ·   Recent runs {len(recent_runs)}"
        )
        for rule in rules:
            state = self.runtime.watch_store.get_state(rule.rule_id)
            tag = "enabled" if rule.enabled else "disabled"
            self.watch_rule_tree.insert(
                "",
                "end",
                iid=rule.rule_id,
                values=watch_rule_row(rule, state),
                tags=(tag,),
            )
        self.watch_rule_tree.tag_configure("enabled", foreground="#166534")
        self.watch_rule_tree.tag_configure("disabled", foreground="#6B7280")

        self.watch_history_tree.delete(*self.watch_history_tree.get_children())
        for history in recent_runs:
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

    def _refresh_dashboard_metrics(self) -> None:
        if not hasattr(self, "dashboard_patents_var"):
            return
        store = self.runtime.library_store
        self.dashboard_patents_var.set(str(store.count_patents()))
        self.dashboard_families_var.set(str(len(store.list_families(limit=500))))
        self.dashboard_watch_var.set(str(len(self.runtime.watch_store.list_rules())))
        self.dashboard_evidence_var.set(str(len(store.list_evidence(limit=1000))))

    def refresh_library(self) -> None:
        self._refresh_dashboard_metrics()
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

    def choose_library_root(self) -> None:
        selected = filedialog.askdirectory(
            initialdir=self.library_root_var.get() or self.runtime.paths.downloads,
            title="选择 LocalLibrary 专利库目录",
        )
        if not selected:
            return
        root = self.runtime.set_library_root(selected)
        self.library_root_var.set(str(root))
        summary = sync_library_root(
            self.runtime.library_store,
            root,
            self.runtime.search_service.company_registry
            if self.runtime.search_service
            else None,
        )
        self.refresh_library()
        message = (
            f"LocalLibrary 已同步：{summary.folders} 个公司目录 · "
            f"{summary.imported} 条专利 · {summary.attached_pdfs} 个 PDF"
        )
        if summary.unknown_folders:
            message += f" · 待核目录 {len(summary.unknown_folders)}"
        self._set_status(message)

    def enrich_library_metadata(self) -> None:
        service = self.runtime.library_enrichment_service
        if service is None:
            messagebox.showwarning("不可用", "本地库补全服务当前不可用。")
            return
        self.library_enrich_button.state(["disabled"])
        self.library_enrich_status_var.set("元数据补全：运行中…")
        self._set_status("正在补全 LocalLibrary 元数据…")

        async def task():
            return await service.enrich_incomplete(limit=500)

        def success(summary) -> None:
            self.library_enrich_button.state(["!disabled"])
            self.library_enrich_status_var.set(
                f"补全 {summary.enriched} · 失败 {summary.failed} · "
                f"无变化 {summary.unchanged}"
            )
            self.refresh_library()
            self._set_status(f"LocalLibrary 元数据补全完成：{summary.enriched} 条更新")

        def failed(exc: Exception) -> None:
            self.library_enrich_button.state(["!disabled"])
            self.library_enrich_status_var.set("元数据补全：失败")
            self._network_error("本地库补全失败", exc)

        run_async_in_thread(
            task,
            on_success=success,
            on_error=failed,
            schedule_ui=self._ui_callbacks.submit,
        )

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
