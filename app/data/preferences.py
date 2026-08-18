from pathlib import Path

from app.data.sqlite import SqliteDatabase


class PreferencesRepository:
    def __init__(self, database_path):
        path = Path(database_path)
        path.parent.mkdir(parents=True, exist_ok=True)
        self.database = SqliteDatabase(path)
        with self.database.connect() as connection:
            connection.execute(
                """
                CREATE TABLE IF NOT EXISTS app_preferences (
                    key TEXT PRIMARY KEY,
                    value TEXT NOT NULL,
                    updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
                )
                """
            )
            connection.commit()

    def all(self):
        with self.database.connect(readonly=True) as connection:
            rows = connection.execute("SELECT key, value FROM app_preferences").fetchall()
        return {row["key"]: row["value"] for row in rows}

    def save(self, values):
        with self.database.connect() as connection:
            connection.executemany(
                """
                INSERT INTO app_preferences (key, value) VALUES (?, ?)
                ON CONFLICT(key) DO UPDATE SET
                    value = excluded.value,
                    updated_at = CURRENT_TIMESTAMP
                """,
                ((str(key), str(value)) for key, value in values.items()),
            )
            connection.commit()
        return self.all()

