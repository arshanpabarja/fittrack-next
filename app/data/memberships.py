from pathlib import Path
import json
import os
from threading import RLock
import uuid

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
    transaction_id TEXT,
    renewed_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);
CREATE INDEX IF NOT EXISTS idx_membership_renewals_member
ON membership_renewals(member_id, renewed_at);

CREATE TABLE IF NOT EXISTS renewal_transactions (
    transaction_id TEXT PRIMARY KEY,
    member_id INTEGER NOT NULL,
    previous_plan TEXT NOT NULL,
    new_plan TEXT NOT NULL,
    carried_sessions INTEGER NOT NULL DEFAULT 0,
    membership_started_at TEXT NOT NULL,
    requested_amount INTEGER NOT NULL DEFAULT 0,
    paid_amount INTEGER NOT NULL DEFAULT 0,
    payment_reference TEXT NOT NULL DEFAULT '',
    status TEXT NOT NULL,
    last_error TEXT NOT NULL DEFAULT '',
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);
CREATE INDEX IF NOT EXISTS idx_renewal_transactions_status
ON renewal_transactions(status, created_at);
"""


class MembershipRepository:
    def __init__(self, database_path):
        path = Path(database_path)
        path.parent.mkdir(parents=True, exist_ok=True)
        self.database = SqliteDatabase(path)
        self.emergency_path = path.with_name("renewal_emergency.jsonl")
        self.emergency_lock = RLock()
        with self.database.connect() as connection:
            connection.executescript(SCHEMA)
            columns = {
                row["name"]
                for row in connection.execute("PRAGMA table_info(membership_renewals)")
            }
            if "transaction_id" not in columns:
                connection.execute(
                    "ALTER TABLE membership_renewals ADD COLUMN transaction_id TEXT"
                )
            connection.execute(
                """
                CREATE UNIQUE INDEX IF NOT EXISTS idx_membership_renewals_transaction
                ON membership_renewals(transaction_id)
                WHERE transaction_id IS NOT NULL
                """
            )
            connection.commit()

    def record_emergency_receipt(self, transaction_id, *, paid_amount, payment_reference):
        """Fsync a minimal receipt before the second database write."""
        payload = json.dumps(
            {
                "transaction_id": str(transaction_id),
                "paid_amount": int(paid_amount),
                "payment_reference": str(payment_reference),
            },
            ensure_ascii=False,
            separators=(",", ":"),
        )
        with self.emergency_lock:
            self.emergency_path.parent.mkdir(parents=True, exist_ok=True)
            with self.emergency_path.open("a", encoding="utf-8") as stream:
                stream.write(payload + "\n")
                stream.flush()
                os.fsync(stream.fileno())

    def _transaction_status(self, transaction_id):
        with self.database.connect(readonly=True) as connection:
            row = connection.execute(
                "SELECT status FROM renewal_transactions WHERE transaction_id=?",
                (str(transaction_id),),
            ).fetchone()
        return row["status"] if row else None

    def clear_emergency_receipt(self, transaction_id):
        with self.emergency_lock:
            if not self.emergency_path.is_file():
                return
            transaction_id = str(transaction_id)
            remaining = []
            for line in self.emergency_path.read_text(encoding="utf-8").splitlines():
                try:
                    if json.loads(line).get("transaction_id") == transaction_id:
                        continue
                except (ValueError, TypeError):
                    pass
                remaining.append(line)
            temporary = self.emergency_path.with_suffix(".tmp")
            if remaining:
                with temporary.open("w", encoding="utf-8") as stream:
                    stream.write("\n".join(remaining) + "\n")
                    stream.flush()
                    os.fsync(stream.fileno())
                os.replace(temporary, self.emergency_path)
            else:
                self.emergency_path.unlink(missing_ok=True)
                temporary.unlink(missing_ok=True)

    def import_emergency_receipts(self):
        with self.emergency_lock:
            if not self.emergency_path.is_file():
                return 0
            imported = 0
            lines = self.emergency_path.read_text(encoding="utf-8").splitlines()
            for line in lines:
                try:
                    payload = json.loads(line)
                    transaction_id = payload["transaction_id"]
                    status = self._transaction_status(transaction_id)
                    if status == "payment_pending":
                        self.mark_payment_approved(
                            transaction_id,
                            paid_amount=payload["paid_amount"],
                            payment_reference=payload["payment_reference"],
                        )
                        imported += 1
                    if status is None:
                        continue
                    self.clear_emergency_receipt(transaction_id)
                except (OSError, ValueError, TypeError, KeyError, RuntimeError):
                    # Keep the line intact; the next startup can retry it.
                    continue
            return imported

    def prepare_renewal(
        self,
        *,
        member_id,
        previous_plan,
        new_plan,
        carried_sessions,
        membership_started_at,
        requested_amount,
    ):
        """Persist intent before contacting POS so a successful charge is never invisible."""
        transaction_id = uuid.uuid4().hex
        with self.database.connect() as connection:
            connection.execute("BEGIN IMMEDIATE")
            connection.execute(
                """
                INSERT INTO renewal_transactions (
                    transaction_id, member_id, previous_plan, new_plan,
                    carried_sessions, membership_started_at, requested_amount,
                    status
                ) VALUES (?, ?, ?, ?, ?, ?, ?, 'payment_pending')
                """,
                (
                    transaction_id,
                    int(member_id),
                    str(previous_plan),
                    str(new_plan),
                    int(carried_sessions),
                    normalize_membership_datetime(membership_started_at),
                    int(requested_amount),
                ),
            )
            connection.commit()
        return transaction_id

    def mark_payment_approved(self, transaction_id, *, paid_amount, payment_reference):
        with self.database.connect() as connection:
            connection.execute("BEGIN IMMEDIATE")
            cursor = connection.execute(
                """
                UPDATE renewal_transactions
                SET paid_amount = ?, payment_reference = ?, status = 'payment_approved',
                    last_error = '', updated_at = CURRENT_TIMESTAMP
                WHERE transaction_id = ? AND status = 'payment_pending'
                """,
                (int(paid_amount), str(payment_reference), str(transaction_id)),
            )
            if cursor.rowcount != 1:
                raise RuntimeError("وضعیت تراکنش تمدید برای ثبت تأیید پرداخت معتبر نیست.")
            connection.commit()

    def mark_payment_failed(self, transaction_id, error):
        with self.database.connect() as connection:
            connection.execute(
                """
                UPDATE renewal_transactions
                SET status = 'payment_failed', last_error = ?, updated_at = CURRENT_TIMESTAMP
                WHERE transaction_id = ? AND status = 'payment_pending'
                """,
                (str(error)[:1000], str(transaction_id)),
            )
            connection.commit()

    def record_pending_error(self, transaction_id, error):
        with self.database.connect() as connection:
            connection.execute(
                """
                UPDATE renewal_transactions
                SET last_error=?, updated_at=CURRENT_TIMESTAMP
                WHERE transaction_id=? AND status='payment_pending'
                """,
                (str(error)[:1000], str(transaction_id)),
            )
            connection.commit()

    def mark_member_updated(self, transaction_id):
        with self.database.connect() as connection:
            connection.execute("BEGIN IMMEDIATE")
            cursor = connection.execute(
                """
                UPDATE renewal_transactions
                SET status = 'member_updated', last_error = '', updated_at = CURRENT_TIMESTAMP
                WHERE transaction_id = ? AND status IN ('payment_approved', 'member_updated')
                """,
                (str(transaction_id),),
            )
            if cursor.rowcount != 1:
                raise RuntimeError("تراکنش تأییدشده برای ثبت تمدید عضو پیدا نشد.")
            connection.commit()

    def record_recovery_error(self, transaction_id, error):
        with self.database.connect() as connection:
            connection.execute(
                """
                UPDATE renewal_transactions
                SET last_error = ?, updated_at = CURRENT_TIMESTAMP
                WHERE transaction_id = ? AND status IN ('payment_approved', 'member_updated')
                """,
                (str(error)[:1000], str(transaction_id)),
            )
            connection.commit()

    def recoverable_renewals(self):
        with self.database.connect(readonly=True) as connection:
            return connection.execute(
                """
                SELECT * FROM renewal_transactions
                WHERE status IN ('payment_approved', 'member_updated')
                ORDER BY created_at, transaction_id
                """
            ).fetchall()

    def incomplete_renewals(self):
        with self.database.connect(readonly=True) as connection:
            return connection.execute(
                """
                SELECT * FROM renewal_transactions
                WHERE status != 'completed' AND status != 'payment_failed'
                ORDER BY created_at DESC, transaction_id DESC
                """
            ).fetchall()

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
        transaction_id=None,
    ):
        with self.database.connect() as connection:
            connection.execute("BEGIN IMMEDIATE")
            connection.execute(
                """
                INSERT OR IGNORE INTO membership_renewals (
                    member_id, previous_plan, new_plan, carried_sessions,
                    membership_started_at, paid_amount, payment_reference,
                    transaction_id
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    int(member_id),
                    str(previous_plan),
                    str(new_plan),
                    int(carried_sessions),
                    normalize_membership_datetime(membership_started_at),
                    int(paid_amount),
                    str(payment_reference),
                    str(transaction_id) if transaction_id else None,
                ),
            )
            connection.execute(
                "DELETE FROM membership_grace WHERE member_id = ?",
                (int(member_id),),
            )
            if transaction_id:
                cursor = connection.execute(
                    """
                    UPDATE renewal_transactions
                    SET status = 'completed', last_error = '', updated_at = CURRENT_TIMESTAMP
                    WHERE transaction_id = ? AND status IN ('payment_approved', 'member_updated', 'completed')
                    """,
                    (str(transaction_id),),
                )
                if cursor.rowcount != 1:
                    raise RuntimeError("تراکنش تمدید برای تکمیل تاریخچه پیدا نشد.")
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
