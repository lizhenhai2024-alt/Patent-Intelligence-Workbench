import asyncio
import threading

from app.desktop.async_runner import run_async_in_thread


def test_async_runner_delivers_success_callback():
    completed = threading.Event()
    received = []

    async def task():
        await asyncio.sleep(0)
        return 42

    def schedule(callback):
        callback()

    run_async_in_thread(
        task,
        on_success=lambda value: (received.append(value), completed.set()),
        on_error=lambda _error: completed.set(),
        schedule_ui=schedule,
    )

    assert completed.wait(timeout=2)
    assert received == [42]


def test_async_runner_delivers_original_exception():
    completed = threading.Event()
    errors = []

    async def task():
        raise RuntimeError("boom")

    def on_error(error):
        errors.append(error)
        completed.set()

    run_async_in_thread(
        task,
        on_success=lambda _value: completed.set(),
        on_error=on_error,
        schedule_ui=lambda callback: callback(),
    )

    assert completed.wait(timeout=2)
    assert isinstance(errors[0], RuntimeError)
    assert str(errors[0]) == "boom"
