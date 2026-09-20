import threading

from app.library.models import LibraryQuery
from app.library.store import SQLitePatentLibrary
from app.watch.state import SQLiteWatchStateStore


def _run_in_worker(callback):
    completed = threading.Event()
    errors = []

    def worker():
        try:
            callback()
        except Exception as exc:
            errors.append(exc)
        finally:
            completed.set()

    thread = threading.Thread(target=worker)
    thread.start()
    assert completed.wait(5)
    thread.join(timeout=1)
    assert errors == []


def test_library_store_can_be_read_from_background_thread(tmp_path):
    store = SQLitePatentLibrary(tmp_path / "workbench.db")
    try:
        _run_in_worker(lambda: store.query(LibraryQuery(limit=10)))
    finally:
        store.close()


def test_watch_store_can_be_read_from_background_thread(tmp_path):
    store = SQLiteWatchStateStore(tmp_path / "workbench.db")
    try:
        _run_in_worker(store.list_rules)
    finally:
        store.close()
