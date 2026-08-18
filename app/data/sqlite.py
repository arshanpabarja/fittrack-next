from contextlib import contextmanager
from pathlib import Path
import sqlite3
import time


class SqliteDatabase:
    def __init__(self, path: Path):
        self.path = Path(path)

    @contextmanager
    def connect(self, *, readonly=False, max_query_ms=None):
        if readonly:
            uri = f"file:{self.path.resolve().as_posix()}?mode=ro"
            connection = sqlite3.connect(uri, uri=True, timeout=3)
        else:
            connection = sqlite3.connect(self.path, timeout=8)
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA busy_timeout = 8000")
        if max_query_ms:
            started = time.monotonic()
            connection.set_progress_handler(
                lambda: 1 if (time.monotonic() - started) * 1000 > max_query_ms else 0,
                2_000,
            )
        try:
            yield connection
        finally:
            connection.close()

