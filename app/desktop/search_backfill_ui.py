"""专利检索 → 确认后批量补库 (SPEC-library-backfill.md, 覆盖率检查与确认后补库)."""

from __future__ import annotations

import threading
import tkinter as tk
from tkinter import messagebox, ttk

from app.domain.family import FamilyType
from app.library import fulltext, search_backfill
from app.library.service import PatentLibraryService
from app.library.workbench import preferred_library_pdf


def build_search_backfill_controls(app, parent) -> None:
    row = ttk.Frame(parent, style="Surface.TFrame")
    row.pack(fill="x", pady=(6, 0))
    app.search_backfill_button = ttk.Button(
        row, text="批量补库", command=lambda: start_search_backfill(app), style="Ghost.TButton"
    )
    app.search_backfill_button.pack(side="left")
    app.search_backfill_cancel_button = ttk.Button(
        row, text="取消", command=lambda: cancel_search_backfill(app), style="Quiet.TButton",
        state="disabled",
    )
    app.search_backfill_cancel_button.pack(side="left", padx=(6, 0))
    app.search_backfill_status_var = tk.StringVar(value="")
    ttk.Label(
        row, textvariable=app.search_backfill_status_var, style="SurfaceSubtle.TLabel"
    ).pack(side="left", padx=(10, 0))
    app._search_backfill_cancel = None


def _current_expression(app) -> dict | None:
    service = app.runtime.search_service
    if service is None:
        messagebox.showwarning("未配置", app.runtime.search_status)
        return None
    query = app.search_query_var.get().strip()
    if query == "输入专利号、关键词或公司名称":
        query = ""
    company = app.search_company_var.get().strip() or None
    if company:
        try:
            company = service.company_registry.get(company).display_name
        except KeyError:
            pass
    if not company and query:
        try:
            company = service.company_registry.get(query).display_name
            query = ""
        except KeyError:
            pass
    if not company:
        messagebox.showinfo("请先指定公司", "批量补库需要一个明确的公司（检索框输入或下拉选择）。")
        return None
    scope = app.search_scope_var.get().strip()
    portfolio_scope = None
    technology_terms: tuple[str, ...] = ()
    if scope == "悬架与减振器":
        portfolio_scope = "suspension portfolio"
    elif scope == "具体技术主题" and query:
        technology_terms = (query,)
    raw_jurisdictions = app.search_jurisdiction_var.get().split(",")
    jurisdictions = tuple(
        item.strip().upper() for item in raw_jurisdictions if item.strip()
    )
    return {
        "query": query if scope == "具体技术主题" else "",
        "company": company,
        "portfolio_scope": portfolio_scope,
        "technology_terms": technology_terms,
        "jurisdictions": jurisdictions,
    }


def start_search_backfill(app) -> None:
    if app._search_backfill_cancel is not None:
        return
    expression = _current_expression(app)
    if expression is None:
        return
    _confirm_dialog(app, expression)


def _confirm_dialog(app, expression: dict) -> None:
    dialog = tk.Toplevel(app)
    dialog.title("确认批量补库")
    dialog.transient(app)
    ttk.Label(
        dialog,
        padding=(12, 10, 12, 4),
        wraplength=460,
        justify="left",
        text=(
            f"公司：{expression['company']}　"
            f"国家/局：{', '.join(expression['jurisdictions']) or '不限'}\n"
            "确认后程序会联网检索，本地已有的公开号自动跳过，"
            "新的会解析专利族、下载 PDF 并写入全文索引。"
        ),
    ).pack(anchor="w")
    limit_row = ttk.Frame(dialog, padding=(12, 4))
    limit_row.pack(fill="x")
    ttk.Label(limit_row, text="本次上限：").pack(side="left")
    limit_var = tk.IntVar(value=search_backfill.DEFAULT_LIMIT)
    ttk.Spinbox(
        limit_row, from_=1, to=search_backfill.HARD_LIMIT, textvariable=limit_var, width=8
    ).pack(side="left")

    def finish(approved: bool) -> None:
        dialog.destroy()
        if approved:
            _run(app, expression, max(1, limit_var.get()))

    buttons = ttk.Frame(dialog, padding=12)
    buttons.pack(fill="x")
    ttk.Button(buttons, text="确认，开始联网补库", command=lambda: finish(True)).pack(side="right")
    ttk.Button(buttons, text="取消", command=lambda: finish(False)).pack(side="right", padx=8)
    dialog.protocol("WM_DELETE_WINDOW", lambda: finish(False))


def _run(app, expression: dict, limit: int) -> None:
    runtime = app.runtime
    cancel = threading.Event()
    app._search_backfill_cancel = cancel
    app.search_backfill_button.state(["disabled"])
    app.search_backfill_cancel_button.state(["!disabled"])
    app.search_backfill_status_var.set("正在检索…")

    def progress(position: int, total: int, number: str) -> None:
        text = f"正在补库：{position} / {total}（{number}）"
        app._ui_callbacks.submit(lambda: app.search_backfill_status_var.set(text))

    def worker() -> None:
        import asyncio

        service = PatentLibraryService(runtime.library_store)
        try:
            summary = asyncio.run(
                search_backfill.run_search_backfill(
                    service,
                    runtime.search_service,
                    runtime.family_resolver,
                    runtime.family_downloader,
                    runtime.library_root or runtime.paths.downloads,
                    query=expression["query"],
                    company=expression["company"],
                    portfolio_scope=expression["portfolio_scope"],
                    technology_terms=expression["technology_terms"],
                    jurisdictions=expression["jurisdictions"],
                    limit=limit,
                    family_type=FamilyType.DOCDB_SIMPLE,
                    progress=progress,
                    should_cancel=cancel.is_set,
                )
            )
        except Exception as exc:
            app._ui_callbacks.submit(lambda error=exc: _finish(app, f"补库失败：{error}"))
            return
        log_dir = runtime.paths.root / "backfill_runs"
        search_backfill.write_task_log(log_dir, summary, limit=limit)
        if summary.added:
            try:
                added_numbers = [
                    o.publication_number for o in summary.outcomes if o.result == "added"
                ]
                items = []
                for number in added_numbers:
                    patent = runtime.library_store.get_patent(number)
                    if patent is not None:
                        items.append((number, preferred_library_pdf(patent)))
                fulltext.index_pdfs(runtime.library_store.connection, items)
            except Exception:
                pass
        head = "已取消" if summary.cancelled else "补库完成"
        total_note = f"，外部约 {summary.external_total} 件" if summary.external_total else ""
        message = (
            f"{head}：新增 {summary.added} 件，已在本地跳过 {summary.already_local} 件，"
            f"专利族解析失败 {summary.family_failed} 件，下载失败 {summary.download_failed} 件"
            f"{total_note}"
        )
        app._ui_callbacks.submit(lambda: _finish(app, message))

    threading.Thread(target=worker, daemon=True).start()


def cancel_search_backfill(app) -> None:
    if app._search_backfill_cancel is not None:
        app._search_backfill_cancel.set()


def _finish(app, message: str) -> None:
    app._search_backfill_cancel = None
    app.search_backfill_button.state(["!disabled"])
    app.search_backfill_cancel_button.state(["disabled"])
    app.search_backfill_status_var.set(message)
    app._set_status(message)
    app.refresh_library()
