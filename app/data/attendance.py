import json
from pathlib import Path
from datetime import datetime, timedelta

from app.data.sqlite import SqliteDatabase
from app.domain.errors import FitTrackError
from app.domain.models import AttendancePageResult, AttendanceRecord


SCHEMA = """
CREATE TABLE IF NOT EXISTS attendance_sessions (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    member_id INTEGER NOT NULL,
    full_name TEXT NOT NULL,
    mobile TEXT NOT NULL,
    plan TEXT NOT NULL,
    checked_in_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    checked_out_at TEXT,
    locker_id INTEGER
);
CREATE UNIQUE INDEX IF NOT EXISTS uq_active_member
ON attendance_sessions(mobile) WHERE checked_out_at IS NULL;
CREATE INDEX IF NOT EXISTS idx_attendance_date
ON attendance_sessions(checked_in_at);

CREATE TABLE IF NOT EXISTS lockers (
    locker_id INTEGER PRIMARY KEY,
    status TEXT NOT NULL DEFAULT 'empty',
    attendance_id INTEGER,
    FOREIGN KEY(attendance_id) REFERENCES attendance_sessions(id)
);

CREATE TABLE IF NOT EXISTS sync_outbox (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    event_type TEXT NOT NULL,
    payload_json TEXT NOT NULL,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    processed_at TEXT,
    last_error TEXT NOT NULL DEFAULT ''
);
"""


class AttendanceRepository:
    def __init__(self, database_path, locker_count=72):
        path = Path(database_path)
        path.parent.mkdir(parents=True, exist_ok=True)
        self.database = SqliteDatabase(path)
        with self.database.connect() as connection:
            connection.executescript(SCHEMA)
            connection.executemany(
                "INSERT OR IGNORE INTO lockers (locker_id) VALUES (?)",
                ((number,) for number in range(1, locker_count + 1)),
            )
            connection.commit()

    def check_in(self, member, timestamp):
        with self.database.connect() as connection:
            connection.execute("BEGIN IMMEDIATE")
            active = connection.execute(
                "SELECT id FROM attendance_sessions WHERE mobile = ? AND checked_out_at IS NULL",
                (member.mobile,),
            ).fetchone()
            if active:
                raise FitTrackError("این عضو هم‌اکنون داخل باشگاه ثبت شده است.")
            locker = connection.execute(
                "SELECT locker_id FROM lockers WHERE status = 'empty' ORDER BY locker_id LIMIT 1"
            ).fetchone()
            if not locker:
                raise FitTrackError("کمد خالی موجود نیست.")
            locker_id = int(locker["locker_id"])
            cursor = connection.execute(
                """
                INSERT INTO attendance_sessions (
                    member_id, full_name, mobile, plan, checked_in_at, locker_id
                ) VALUES (?, ?, ?, ?, ?, ?)
                """,
                (member.id, member.full_name, member.mobile, member.plan, timestamp, locker_id),
            )
            attendance_id = int(cursor.lastrowid)
            connection.execute(
                "UPDATE lockers SET status = 'occupied', attendance_id = ? WHERE locker_id = ?",
                (attendance_id, locker_id),
            )
            connection.execute(
                "INSERT INTO sync_outbox (event_type, payload_json) VALUES ('increment_session', ?)",
                (json.dumps({"member_id": member.id}),),
            )
            connection.commit()
        return attendance_id, locker_id

    def check_out(self, mobile, timestamp):
        with self.database.connect() as connection:
            connection.execute("BEGIN IMMEDIATE")
            row = connection.execute(
                """
                SELECT id, locker_id FROM attendance_sessions
                WHERE mobile = ? AND checked_out_at IS NULL
                ORDER BY id DESC LIMIT 1
                """,
                (mobile,),
            ).fetchone()
            if not row:
                raise FitTrackError("ورود فعالی برای این عضو پیدا نشد.")
            connection.execute(
                "UPDATE attendance_sessions SET checked_out_at = ? WHERE id = ?",
                (timestamp, row["id"]),
            )
            if row["locker_id"] is not None:
                connection.execute(
                    "UPDATE lockers SET status = 'empty', attendance_id = NULL WHERE locker_id = ?",
                    (row["locker_id"],),
                )
            connection.commit()
        return int(row["id"]), row["locker_id"]

    def auto_checkout(self, minutes=60, now=None):
        now = now or datetime.now()
        cutoff = (now - timedelta(minutes=int(minutes))).strftime("%Y-%m-%d %H:%M:%S")
        timestamp = now.strftime("%Y-%m-%d %H:%M:%S")
        with self.database.connect() as connection:
            connection.execute("BEGIN IMMEDIATE")
            rows = connection.execute(
                """
                SELECT id, locker_id FROM attendance_sessions
                WHERE checked_out_at IS NULL AND checked_in_at <= ?
                """,
                (cutoff,),
            ).fetchall()
            for row in rows:
                connection.execute(
                    "UPDATE attendance_sessions SET checked_out_at = ? WHERE id = ?",
                    (timestamp, row["id"]),
                )
                if row["locker_id"] is not None:
                    connection.execute(
                        "UPDATE lockers SET status = 'empty', attendance_id = NULL WHERE locker_id = ?",
                        (row["locker_id"],),
                    )
            connection.commit()
        return len(rows)

    def summary(self):
        with self.database.connect(readonly=True) as connection:
            inside = connection.execute(
                "SELECT COUNT(*) FROM attendance_sessions WHERE checked_out_at IS NULL"
            ).fetchone()[0]
            free = connection.execute(
                "SELECT COUNT(*) FROM lockers WHERE status = 'empty'"
            ).fetchone()[0]
        return {"inside": int(inside), "free_lockers": int(free)}

    def dashboard_counts(self, today_prefix):
        with self.database.connect(readonly=True) as connection:
            inside = connection.execute(
                "SELECT COUNT(*) FROM attendance_sessions WHERE checked_out_at IS NULL"
            ).fetchone()[0]
            today = connection.execute(
                "SELECT COUNT(*) FROM attendance_sessions WHERE checked_in_at LIKE ?",
                (today_prefix,),
            ).fetchone()[0]
        return int(inside), int(today)

    def pending_outbox(self, limit=100):
        with self.database.connect(readonly=True) as connection:
            return connection.execute(
                "SELECT id, event_type, payload_json FROM sync_outbox WHERE processed_at IS NULL ORDER BY id LIMIT ?",
                (int(limit),),
            ).fetchall()

    def mark_outbox_processed(self, event_id):
        with self.database.connect() as connection:
            connection.execute(
                "UPDATE sync_outbox SET processed_at = CURRENT_TIMESTAMP, last_error = '' WHERE id = ?",
                (int(event_id),),
            )
            connection.commit()

    def mark_outbox_error(self, event_id, message):
        with self.database.connect() as connection:
            connection.execute(
                "UPDATE sync_outbox SET last_error = ? WHERE id = ?",
                (str(message)[:500], int(event_id)),
            )
            connection.commit()

    @staticmethod
    def _record(row):
        return AttendanceRecord(
            id=int(row["id"]),
            full_name=row["full_name"],
            mobile=row["mobile"],
            plan=row["plan"],
            checked_in_at=row["checked_in_at"],
            checked_out_at=row["checked_out_at"] or "",
            locker_id=row["locker_id"],
        )

    def list_sessions(self, search="", page=1, page_size=50):
        page = max(1, int(page))
        page_size = min(200, max(10, int(page_size)))
        query = search.strip()
        where = ""
        parameters = []
        if query:
            where = "WHERE full_name LIKE ? OR mobile LIKE ?"
            token = f"%{query}%"
            parameters.extend([token, token])
        parameters.extend([page_size + 1, (page - 1) * page_size])
        with self.database.connect(readonly=True) as connection:
            rows = connection.execute(
                f"""
                SELECT id, full_name, mobile, plan, checked_in_at,
                       checked_out_at, locker_id
                FROM attendance_sessions {where}
                ORDER BY id DESC LIMIT ? OFFSET ?
                """,
                parameters,
            ).fetchall()
        items = tuple(self._record(row) for row in rows[:page_size])
        return AttendancePageResult(items, page, page_size, len(rows) > page_size)

    def all_sessions(self, batch_size=500):
        offset = 0
        while True:
            with self.database.connect(readonly=True) as connection:
                rows = connection.execute(
                    """
                    SELECT id, full_name, mobile, plan, checked_in_at,
                           checked_out_at, locker_id
                    FROM attendance_sessions ORDER BY id DESC LIMIT ? OFFSET ?
                    """,
                    (int(batch_size), offset),
                ).fetchall()
            if not rows:
                return
            for row in rows:
                yield self._record(row)
            offset += len(rows)
