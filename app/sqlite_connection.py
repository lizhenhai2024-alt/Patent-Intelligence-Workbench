"""Thread-local SQLite connections for desktop/background worker safety."""

from __future__ import annotations

import sqlite3
import threading
from pathlib import Path


class ThreadLocalSQLite:
    """Provide one SQLite connection per calling thread for a shared database path."""

    def __init__(self, path: str | Path):
        self.path = Path(path)
        self._local = threading.local()
        self._connections: list[sqlite3.Connection] = []
        self._lock = threading.Lock()

    def get(self) -> sqlite3.Connection:
        connection = getattr(self._local, "connection", None)
        if connection is not None:
            return connection

        connection = sqlite3.connect(
            self.path,
            timeout=30.0,
            check_same_thread=False,
        )
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA foreign_keys = ON")
        connection.execute("PRAGMA busy_timeout = 5000")
        self._local.connection = connection

        with self._lock:
            self._connections.append(connection)
        return connection

    def close_all(self) -> None:
        with self._lock:
            connections = tuple(self._connections)
            self._connections.clear()

        for connection in connections:
            try:
                connection.close()
            except sqlite3.Error:
                pass

        if hasattr(self._local, "connection"):
            del self._local.connection
