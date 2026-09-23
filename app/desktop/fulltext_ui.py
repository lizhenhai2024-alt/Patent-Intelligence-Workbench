"""本地专利库 → 更新全文索引 (background, with progress and cancel)."""

from __future__ import annotations

import threading
import tkinter as tk
from tkinter import ttk

from app.library import fulltext
from app.library.models import LibraryQuery
from app.library.workbench import preferred_library_pdf

_STATUS_NAMES = {
    fulltext.STATUS_OK: "完整",
    fulltext.STATUS_PARTIAL: "部分",
    fulltext.STATUS_NEEDS_OCR: "需要 OCR",
    fulltext.STATUS_FAILED: "失败",
}


def coverage_text(app) -> str:
    info = fulltext.coverage(app.runtime.library_store.connection)
    parts = "、".join(
        f"{_STATUS_NAMES.get(k, k)} {v}" for k, v in sorted(info["statuses"].items())
    )
    return (
        f"全文索引：已索引 {info['indexed']} / {info['publications']} 件"
        + (f"（{parts}）" if parts else "")
        + ("" if info["trigram"] else "；当前 SQLite 不支持 trigram，检索将较慢")
    )


def build_fulltext_controls(app, parent) -> None:
    row = ttk.Frame(parent, style="Surface.TFrame")
    row.pack(fill="x", pady=(8, 0))
    app.fulltext_button = ttk.Button(
        row, text="更新全文索引", command=lambda: run_fulltext_index(app), style="Quiet.TButton"
    )
    app.fulltext_button.pack(side="left")
    app.fulltext_cancel_button = ttk.Button(
        row, text="取消", command=lambda: cancel_fulltext_index(app), style="Quiet.TButton",
        state="disabled",
    )
    app.fulltext_cancel_button.pack(side="left", padx=(6, 0))
    app.fulltext_status_var = tk.StringVar(value=coverage_text(app))
    ttk.Label(row, textvariable=app.fulltext_status_var, style="SurfaceSubtle.TLabel").pack(
        side="left", padx=(10, 0)
    )
    app._fulltext_cancel = None


def run_fulltext_index(app) -> None:
    if app._fulltext_cancel is not None:
        return
    store = app.runtime.library_store
    patents = store.query(LibraryQuery(limit=max(1, store.count_patents())))
    items = [(p.publication_number, preferred_library_pdf(p)) for p in patents]
    total = len(items)
    cancel = threading.Event()
    app._fulltext_cancel = cancel
    app.fulltext_button.state(["disabled"])
    app.fulltext_cancel_button.state(["!disabled"])
    app.fulltext_status_var.set(f"正在建立全文索引：0 / {total}")

    def progress(position: int, number: str) -> None:
        text = f"正在建立全文索引：{position} / {total}（{number}）"
        app._ui_callbacks.submit(lambda: app.fulltext_status_var.set(text))

    def worker() -> None:
        try:
            summary = fulltext.index_pdfs(
                store.connection, items, progress=progress, should_cancel=cancel.is_set
            )
        except Exception as exc:
            app._ui_callbacks.submit(lambda error=exc: _finish(app, f"全文索引失败：{error}"))
            return
        head = "已取消" if summary.cancelled else "全文索引完成"
        message = (
            f"{head}：本次解析 {summary.indexed} 件，未变化跳过 {summary.skipped} 件，"
            f"无 PDF {summary.no_pdf} 件"
        )
        app._ui_callbacks.submit(lambda: _finish(app, message))

    threading.Thread(target=worker, daemon=True).start()


def cancel_fulltext_index(app) -> None:
    if app._fulltext_cancel is not None:
        app._fulltext_cancel.set()


def _finish(app, message: str) -> None:
    app._fulltext_cancel = None
    app.fulltext_button.state(["!disabled"])
    app.fulltext_cancel_button.state(["disabled"])
    app.fulltext_status_var.set(f"{message}｜{coverage_text(app)}")
    app._set_status(message)
