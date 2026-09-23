"""本地专利库 → EPO OPS 全文补全 (SPEC-library-backfill.md, 阶段 0)."""

from __future__ import annotations

import threading
import tkinter as tk
from tkinter import ttk

from app.library import backfill
from app.providers.epo_ops import EpoOpsProvider


def build_backfill_controls(app, parent) -> None:
    row = ttk.Frame(parent, style="Surface.TFrame")
    row.pack(fill="x", pady=(4, 0))
    app.backfill_button = ttk.Button(
        row, text="EPO OPS 全文补全", command=lambda: start_backfill(app), style="Quiet.TButton"
    )
    app.backfill_button.pack(side="left")
    app.backfill_cancel_button = ttk.Button(
        row, text="取消", command=lambda: cancel_backfill(app), style="Quiet.TButton",
        state="disabled",
    )
    app.backfill_cancel_button.pack(side="left", padx=(6, 0))
    app.backfill_status_var = tk.StringVar(value="")
    ttk.Label(row, textvariable=app.backfill_status_var, style="SurfaceSubtle.TLabel").pack(
        side="left", padx=(10, 0)
    )
    app._backfill_cancel = None


def start_backfill(app) -> None:
    if app._backfill_cancel is not None:
        return
    credentials = app.runtime.current_epo_credentials()
    if credentials is None:
        app.backfill_status_var.set("未配置 EPO OPS 凭据，请先在设置里填写")
        return
    store = app.runtime.library_store
    items = backfill.candidates(store.connection)
    if not items:
        app.backfill_status_var.set("没有缺全文的公开号，无需补全")
        return
    _confirm_dialog(app, store, credentials, items)


def _confirm_dialog(app, store, credentials, items: list[str]) -> None:
    dialog = tk.Toplevel(app)
    dialog.title("确认 EPO OPS 全文补全")
    dialog.transient(app)
    ttk.Label(
        dialog,
        padding=(12, 10, 12, 4),
        wraplength=440,
        justify="left",
        text=(
            f"本地库中有 {len(items)} 件公开号缺全文或全文不完整。\n"
            "确认后程序会逐个向 EPO OPS 请求官方权利要求书/说明书原文，写入全文索引，"
            "并记录来源；单件失败不影响其它。"
        ),
    ).pack(anchor="w")
    limit_row = ttk.Frame(dialog, padding=(12, 4))
    limit_row.pack(fill="x")
    ttk.Label(limit_row, text="本次上限：").pack(side="left")
    limit_var = tk.IntVar(value=min(backfill.DEFAULT_LIMIT, len(items)))
    ttk.Spinbox(
        limit_row, from_=1, to=min(backfill.HARD_LIMIT, len(items)), textvariable=limit_var,
        width=8,
    ).pack(side="left")

    def finish(approved: bool) -> None:
        dialog.destroy()
        if approved:
            _run(app, store, credentials, items[: max(1, limit_var.get())])

    buttons = ttk.Frame(dialog, padding=12)
    buttons.pack(fill="x")
    ttk.Button(buttons, text="确认，开始联网补全", command=lambda: finish(True)).pack(
        side="right"
    )
    ttk.Button(buttons, text="取消", command=lambda: finish(False)).pack(side="right", padx=8)
    dialog.protocol("WM_DELETE_WINDOW", lambda: finish(False))


def _run(app, store, credentials, items: list[str]) -> None:
    provider = EpoOpsProvider(
        consumer_key=credentials.consumer_key, consumer_secret=credentials.consumer_secret
    )
    total = len(items)
    cancel = threading.Event()
    app._backfill_cancel = cancel
    app.backfill_button.state(["disabled"])
    app.backfill_cancel_button.state(["!disabled"])
    app.backfill_status_var.set(f"正在向 EPO OPS 补全：0 / {total}")

    def progress(position: int, _total: int, number: str) -> None:
        text = f"正在向 EPO OPS 补全：{position} / {total}（{number}）"
        app._ui_callbacks.submit(lambda: app.backfill_status_var.set(text))

    def worker() -> None:
        try:
            summary = backfill.run_backfill(
                store, provider, items, progress=progress, should_cancel=cancel.is_set
            )
        except Exception as exc:
            app._ui_callbacks.submit(lambda error=exc: _finish(app, f"补全失败：{error}"))
            return
        log_dir = app.runtime.paths.root / "backfill_runs"
        backfill.write_task_log(log_dir, summary, limit=total)
        head = "已取消" if summary.cancelled else "补全完成"
        message = (
            f"{head}：新增全文 {summary.filled} 件，EPO OPS 无全文 {summary.no_data} 件，"
            f"失败 {summary.errors} 件"
        )
        app._ui_callbacks.submit(lambda: _finish(app, message))

    threading.Thread(target=worker, daemon=True).start()


def cancel_backfill(app) -> None:
    if app._backfill_cancel is not None:
        app._backfill_cancel.set()


def _finish(app, message: str) -> None:
    app._backfill_cancel = None
    app.backfill_button.state(["!disabled"])
    app.backfill_cancel_button.state(["disabled"])
    app.backfill_status_var.set(message)
    app._set_status(message)
