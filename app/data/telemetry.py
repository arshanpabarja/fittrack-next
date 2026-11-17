import sqlite3
import re
from pathlib import Path

from app.data.sqlite import SqliteDatabase


SCHEMA = """
CREATE TABLE IF NOT EXISTS desktop_log_events (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    level TEXT NOT NULL,
    logger TEXT NOT NULL,
    message TEXT NOT NULL,
    occurred_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    sent_at TEXT
);
CREATE INDEX IF NOT EXISTS idx_desktop_log_unsent
ON desktop_log_events(sent_at, id);
"""


def _redact(message):
    value = str(message)
    patterns = (
        (r"(?i)(authorization\s*[:=]\s*bearer\s+)[^\s,;]+", r"\1[REDACTED]"),
        (r"(?i)((?:api[_-]?token|password|secret)\s*[:=]\s*)[^\s,;]+", r"\1[REDACTED]"),
    )
    for pattern, replacement in patterns:
        value = re.sub(pattern, replacement, value)
    return value


class TelemetryRepository:
    def __init__(self, database_path):
        path = Path(database_path)
        path.parent.mkdir(parents=True, exist_ok=True)
        self.database = SqliteDatabase(path)
        with self.database.connect() as connection:
            connection.executescript(SCHEMA)
            connection.commit()
    def append_log(self, level, logger, message):
        try:
            with self.database.connect() as connection:
                connection.execute(
                    "INSERT INTO desktop_log_events(level,logger,message) VALUES (?,?,?)",
                    (str(level)[:20], str(logger)[:200], _redact(message)[:12000]),
                )
                # Keep bounded local history without deleting unsent events.
                connection.execute(
                    """
                    DELETE FROM desktop_log_events
                    WHERE sent_at IS NOT NULL AND id NOT IN (
                        SELECT id FROM desktop_log_events
                        WHERE sent_at IS NOT NULL ORDER BY id DESC LIMIT 5000
                    )
                    """
                )
                connection.commit()
        except sqlite3.Error:
            # Logging must never recursively log or break the foreground task.
            return

    def pending_logs(self, limit=100):
        with self.database.connect(readonly=True) as connection:
            return connection.execute(
                """
                SELECT id,level,logger,message,occurred_at
                FROM desktop_log_events WHERE sent_at IS NULL
                ORDER BY id LIMIT ?
                """,
                (max(1, min(int(limit), 100)),),
            ).fetchall()

    def mark_sent(self, ids):
        ids = [int(value) for value in ids]
        if not ids:
            return
        placeholders = ",".join("?" for _ in ids)
        with self.database.connect() as connection:
            connection.execute(
                f"UPDATE desktop_log_events SET sent_at=CURRENT_TIMESTAMP WHERE id IN ({placeholders})",
                ids,
            )
            connection.commit()
