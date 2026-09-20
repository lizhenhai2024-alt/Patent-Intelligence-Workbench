"""Run async backend operations outside the Tk main thread."""

from __future__ import annotations

import asyncio
import threading
from collections.abc import Callable
from typing import TypeVar

T = TypeVar("T")


def run_async_in_thread(
    awaitable_factory: Callable[[], object],
    *,
    on_success: Callable[[object], None],
    on_error: Callable[[Exception], None],
    schedule_ui: Callable[[Callable[[], None]], None],
) -> threading.Thread:
    """Run an async factory in a daemon thread and marshal callbacks to Tk."""

    def worker() -> None:
        try:
            result = asyncio.run(awaitable_factory())
        except Exception as exc:
            schedule_ui(lambda: on_error(exc))
            return
        schedule_ui(lambda: on_success(result))

    thread = threading.Thread(target=worker, daemon=True)
    thread.start()
    return thread
