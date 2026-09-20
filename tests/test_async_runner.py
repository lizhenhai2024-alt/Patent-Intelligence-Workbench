import asyncio
import threading

from app.desktop.async_runner import TkCallbackQueue, run_async_in_thread


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


class FakeTkRoot:
    def __init__(self):
        self.scheduled = []
        self.reported = []

    def after(self, _delay, callback):
        self.scheduled.append(callback)

    def report_callback_exception(self, exc_type, exc, traceback):
        self.reported.append((exc_type, exc, traceback))


def test_tk_callback_queue_defers_worker_callback_until_tk_poll():
    root = FakeTkRoot()
    dispatcher = TkCallbackQueue(root, poll_interval_ms=1)
    received = []

    dispatcher.submit(lambda: received.append("done"))

    assert received == []
    assert len(root.scheduled) == 1
    root.scheduled.pop(0)()
    assert received == ["done"]
    dispatcher.close()
