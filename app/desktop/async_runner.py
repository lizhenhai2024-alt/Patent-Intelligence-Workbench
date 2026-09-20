"""Run async backend operations outside the Tk main thread."""

from __future__ import annotations

import asyncio
import threading
from collections.abc import Callable, Coroutine
from typing import Any


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
