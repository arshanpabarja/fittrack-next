from pathlib import Path

from app.data.sqlite import SqliteDatabase
from app.domain.dates import normalize_membership_datetime


SCHEMA = """
CREATE TABLE IF NOT EXISTS membership_grace (
    member_id INTEGER PRIMARY KEY,
    grace_started_at TEXT NOT NULL,
    updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS membership_renewals (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    member_id INTEGER NOT NULL,
    previous_plan TEXT NOT NULL,
    new_plan TEXT NOT NULL,
    carried_sessions INTEGER NOT NULL DEFAULT 0,
    membership_started_at TEXT NOT NULL,
    paid_amount INTEGER NOT NULL DEFAULT 0,
    payment_reference TEXT NOT NULL DEFAULT '',
    renewed_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);
CREATE INDEX IF NOT EXISTS idx_membership_renewals_member
ON membership_renewals(member_id, renewed_at);
"""


class MembershipRepository:
    def __init__(self, database_path):
        path = Path(database_path)
        path.parent.mkdir(parents=True, exist_ok=True)
        self.database = SqliteDatabase(path)
        with self.database.connect() as connection:
            connection.executescript(SCHEMA)
            connection.commit()

    def begin_grace(self, member_id, timestamp):
        with self.database.connect() as connection:
            connection.execute(
                """
                INSERT OR IGNORE INTO membership_grace (
                    member_id, grace_started_at, updated_at
                ) VALUES (?, ?, CURRENT_TIMESTAMP)
                """,
                (int(member_id), normalize_membership_datetime(timestamp)),
            )
            connection.commit()

    def grace_started_at(self, member_id):
        with self.database.connect(readonly=True) as connection:
            row = connection.execute(
                "SELECT grace_started_at FROM membership_grace WHERE member_id = ?",
                (int(member_id),),
            ).fetchone()
        return row["grace_started_at"] if row else None

    def clear_grace(self, member_id):
        with self.database.connect() as connection:
            connection.execute("DELETE FROM membership_grace WHERE member_id = ?", (int(member_id),))
            connection.commit()

    def complete_renewal(
        self,
        *,
        member_id,
        previous_plan,
        new_plan,
        carried_sessions,
        membership_started_at,
        paid_amount,
        payment_reference,
    ):
        with self.database.connect() as connection:
            connection.execute("BEGIN IMMEDIATE")
            connection.execute(
                """
                INSERT INTO membership_renewals (
                    member_id, previous_plan, new_plan, carried_sessions,
                    membership_started_at, paid_amount, payment_reference
                ) VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    int(member_id),
                    str(previous_plan),
                    str(new_plan),
                    int(carried_sessions),
                    normalize_membership_datetime(membership_started_at),
                    int(paid_amount),
                    str(payment_reference),
                ),
            )
            connection.execute(
                "DELETE FROM membership_grace WHERE member_id = ?",
                (int(member_id),),
            )
            connection.commit()

    def renewal_history(self, member_id):
        with self.database.connect(readonly=True) as connection:
            return connection.execute(
                """
                SELECT * FROM membership_renewals
                WHERE member_id = ? ORDER BY id DESC
                """,
                (int(member_id),),
            ).fetchall()
