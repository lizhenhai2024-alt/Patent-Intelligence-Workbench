"""Run async backend operations outside the Tk main thread."""

from __future__ import annotations

import asyncio
import queue
import threading
import tkinter as tk
from collections.abc import Callable, Coroutine
from typing import Any


class TkCallbackQueue:
    """Marshal worker callbacks onto the Tk thread without calling Tk from workers."""

    def __init__(self, root: tk.Misc, *, poll_interval_ms: int = 20):
        if poll_interval_ms < 1:
            raise ValueError("poll_interval_ms must be >= 1")
        self._root = root
        self._poll_interval_ms = poll_interval_ms
        self._queue: queue.SimpleQueue[Callable[[], None]] = queue.SimpleQueue()
        self._closed = False
        self._root.after(self._poll_interval_ms, self._drain)

    def submit(self, callback: Callable[[], None]) -> None:
        if not self._closed:
            self._queue.put(callback)

    def close(self) -> None:
        self._closed = True

    def _drain(self) -> None:
        while True:
            try:
                callback = self._queue.get_nowait()
            except queue.Empty:
                break

            try:
                callback()
            except Exception as exc:
                self._root.report_callback_exception(
                    type(exc),
                    exc,
                    exc.__traceback__,
                )

        if not self._closed:
            self._root.after(self._poll_interval_ms, self._drain)


def run_async_in_thread[T](
    awaitable_factory: Callable[[], Coroutine[Any, Any, T]],
    *,
    on_success: Callable[[T], None],
    on_error: Callable[[Exception], None],
    schedule_ui: Callable[[Callable[[], None]], None],
) -> threading.Thread:
    """Run an async factory in a daemon thread and marshal callbacks to Tk."""

    def worker() -> None:
        try:
            result = asyncio.run(awaitable_factory())
        except Exception as exc:
            schedule_ui(lambda error=exc: on_error(error))
            return
        schedule_ui(lambda value=result: on_success(value))

    thread = threading.Thread(target=worker, daemon=True)
    thread.start()
    return thread
