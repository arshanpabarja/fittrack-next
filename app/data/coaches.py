from pathlib import Path

from app.data.sqlite import SqliteDatabase
from app.domain.errors import RecordNotFound
from app.domain.models import CoachProgram, CoachSummary


SCHEMA = """
CREATE TABLE IF NOT EXISTS coaches (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    full_name TEXT NOT NULL,
    mobile TEXT NOT NULL DEFAULT '',
    specialty TEXT NOT NULL DEFAULT '',
    active INTEGER NOT NULL DEFAULT 1,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);
CREATE UNIQUE INDEX IF NOT EXISTS uq_active_coach_mobile
ON coaches(mobile) WHERE mobile != '' AND active = 1;

CREATE TABLE IF NOT EXISTS coach_programs (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    coach_id INTEGER NOT NULL,
    member_id INTEGER NOT NULL,
    member_name TEXT NOT NULL,
    title TEXT NOT NULL,
    exercises TEXT NOT NULL,
    updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(coach_id, member_id),
    FOREIGN KEY(coach_id) REFERENCES coaches(id)
);
CREATE INDEX IF NOT EXISTS idx_coach_programs_member
ON coach_programs(member_id);
"""


class CoachesRepository:
    def __init__(self, database_path):
        path = Path(database_path)
        path.parent.mkdir(parents=True, exist_ok=True)
        self.database = SqliteDatabase(path)
        with self.database.connect() as connection:
            connection.executescript(SCHEMA)
            connection.commit()

    def list_coaches(self):
        with self.database.connect(readonly=True) as connection:
            rows = connection.execute(
                """
                SELECT c.id, c.full_name, c.mobile, c.specialty,
                       COUNT(p.id) AS athlete_count
                FROM coaches c
                LEFT JOIN coach_programs p ON p.coach_id = c.id
                WHERE c.active = 1
                GROUP BY c.id
                ORDER BY c.full_name
                """
            ).fetchall()
        return tuple(
            CoachSummary(
                id=int(row["id"]),
                full_name=row["full_name"],
                mobile=row["mobile"],
                specialty=row["specialty"],
                athlete_count=int(row["athlete_count"] or 0),
            )
            for row in rows
        )

    def save_coach(self, full_name, mobile, specialty, coach_id=None):
        with self.database.connect() as connection:
            if coach_id is None:
                cursor = connection.execute(
                    "INSERT INTO coaches (full_name, mobile, specialty) VALUES (?, ?, ?)",
                    (full_name, mobile, specialty),
                )
                coach_id = int(cursor.lastrowid)
            else:
                cursor = connection.execute(
                    """
                    UPDATE coaches SET full_name = ?, mobile = ?, specialty = ?,
                        updated_at = CURRENT_TIMESTAMP
                    WHERE id = ? AND active = 1
                    """,
                    (full_name, mobile, specialty, int(coach_id)),
                )
                if cursor.rowcount != 1:
                    raise RecordNotFound("مربی موردنظر پیدا نشد.")
            connection.commit()
        return next(item for item in self.list_coaches() if item.id == int(coach_id))

    def archive_coach(self, coach_id):
        with self.database.connect() as connection:
            cursor = connection.execute(
                "UPDATE coaches SET active = 0, updated_at = CURRENT_TIMESTAMP WHERE id = ? AND active = 1",
                (int(coach_id),),
            )
            if cursor.rowcount != 1:
                raise RecordNotFound("مربی موردنظر پیدا نشد.")
            connection.commit()

    def list_programs(self, coach_id):
        with self.database.connect(readonly=True) as connection:
            rows = connection.execute(
                """
                SELECT id, coach_id, member_id, member_name, title, exercises, updated_at
                FROM coach_programs WHERE coach_id = ? ORDER BY updated_at DESC, id DESC
                """,
                (int(coach_id),),
            ).fetchall()
        return tuple(CoachProgram(**dict(row)) for row in rows)

    def save_program(self, coach_id, member_id, member_name, title, exercises):
        with self.database.connect() as connection:
            connection.execute(
                """
                INSERT INTO coach_programs (
                    coach_id, member_id, member_name, title, exercises
                ) VALUES (?, ?, ?, ?, ?)
                ON CONFLICT(coach_id, member_id) DO UPDATE SET
                    member_name = excluded.member_name,
                    title = excluded.title,
                    exercises = excluded.exercises,
                    updated_at = CURRENT_TIMESTAMP
                """,
                (int(coach_id), int(member_id), member_name, title, exercises),
            )
            connection.commit()

    def delete_program(self, program_id):
        with self.database.connect() as connection:
            cursor = connection.execute(
                "DELETE FROM coach_programs WHERE id = ?", (int(program_id),)
            )
            if cursor.rowcount != 1:
                raise RecordNotFound("برنامه تمرینی پیدا نشد.")
            connection.commit()
