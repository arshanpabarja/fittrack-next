import json
from pathlib import Path

from app.data.sqlite import SqliteDatabase


SCHEMA = """
CREATE TABLE IF NOT EXISTS manager_audit_log (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    actor TEXT NOT NULL,
    action TEXT NOT NULL,
    entity_type TEXT NOT NULL DEFAULT '',
    entity_id TEXT NOT NULL DEFAULT '',
    summary TEXT NOT NULL DEFAULT '',
    before_json TEXT NOT NULL DEFAULT '{}',
    after_json TEXT NOT NULL DEFAULT '{}',
    success INTEGER NOT NULL DEFAULT 1,
    error TEXT NOT NULL DEFAULT '',
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);
CREATE INDEX IF NOT EXISTS idx_manager_audit_created
ON manager_audit_log(created_at DESC, id DESC);
CREATE INDEX IF NOT EXISTS idx_manager_audit_actor
ON manager_audit_log(actor, created_at DESC);
CREATE INDEX IF NOT EXISTS idx_manager_audit_action
ON manager_audit_log(action, created_at DESC);
"""


def _json(value):
    return json.dumps(value or {}, ensure_ascii=False, sort_keys=True, default=str)


class AuditRepository:
    """Append-only manager activity ledger stored in the stable state database."""

    def __init__(self, database_path):
        path = Path(database_path)
        path.parent.mkdir(parents=True, exist_ok=True)
        self.database = SqliteDatabase(path)
        with self.database.connect() as connection:
            connection.executescript(SCHEMA)
            connection.commit()

    def append(
        self,
        *,
        actor,
        action,
        entity_type="",
        entity_id="",
        summary="",
        before=None,
        after=None,
        success=True,
        error="",
    ):
        with self.database.connect() as connection:
            cursor = connection.execute(
                """
                INSERT INTO manager_audit_log (
                    actor, action, entity_type, entity_id, summary,
                    before_json, after_json, success, error
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    str(actor or "اپراتور دستگاه")[:120],
                    str(action)[:80],
                    str(entity_type)[:80],
                    str(entity_id)[:120],
                    str(summary)[:500],
                    _json(before),
                    _json(after),
                    1 if success else 0,
                    str(error)[:1000],
                ),
            )
            connection.commit()
            return cursor.lastrowid

    def list(self, *, search="", action="", limit=500):
        where = []
        parameters = []
        search = str(search or "").strip()
        if search:
            token = f"%{search}%"
            where.append(
                "(actor LIKE ? OR summary LIKE ? OR entity_id LIKE ? OR error LIKE ?)"
            )
            parameters.extend((token, token, token, token))
        if action:
            where.append("action = ?")
            parameters.append(str(action))
        clause = " WHERE " + " AND ".join(where) if where else ""
        parameters.append(max(1, min(int(limit), 1000)))
        with self.database.connect(readonly=True) as connection:
            return connection.execute(
                """
                SELECT * FROM manager_audit_log
                """
                + clause
                + " ORDER BY created_at DESC, id DESC LIMIT ?",
                parameters,
            ).fetchall()
