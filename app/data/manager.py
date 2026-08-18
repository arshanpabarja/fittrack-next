import hashlib

from app.data.sqlite import SqliteDatabase


class ManagerRepository:
    def __init__(self, database_path):
        self.database = SqliteDatabase(database_path)

    def verify(self, username, password):
        digest = hashlib.sha256(password.encode("utf-8")).hexdigest()
        with self.database.connect(readonly=True) as connection:
            row = connection.execute(
                """
                SELECT 1 FROM manager_credentials
                WHERE username = ? AND password_hash = ? LIMIT 1
                """,
                (username, digest),
            ).fetchone()
        return row is not None

