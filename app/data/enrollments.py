import json
from pathlib import Path

from app.data.sqlite import SqliteDatabase
from app.domain.models import EnrollmentState


SCHEMA = """
CREATE TABLE IF NOT EXISTS enrollment_workflows (
    application_id INTEGER PRIMARY KEY,
    application_json TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'started',
    face_embedding TEXT,
    face_image BLOB,
    paid_amount INTEGER NOT NULL DEFAULT 0,
    payment_reference TEXT NOT NULL DEFAULT '',
    legacy_member_id INTEGER,
    last_error TEXT NOT NULL DEFAULT '',
    updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
)
"""


class EnrollmentRepository:
    def __init__(self, database_path):
        path = Path(database_path)
        path.parent.mkdir(parents=True, exist_ok=True)
        self.database = SqliteDatabase(path)
        with self.database.connect() as connection:
            connection.execute(SCHEMA)
            connection.commit()

    @staticmethod
    def _state(row):
        return EnrollmentState(
            application_id=row["application_id"],
            status=row["status"],
            face_captured=bool(row["face_embedding"] and row["face_image"]),
            paid_amount=row["paid_amount"] or 0,
            payment_reference=row["payment_reference"] or "",
            legacy_member_id=row["legacy_member_id"],
            last_error=row["last_error"] or "",
        )

    def start(self, application):
        payload = json.dumps(application.__dict__, ensure_ascii=False)
        with self.database.connect() as connection:
            connection.execute(
                """
                INSERT INTO enrollment_workflows (application_id, application_json)
                VALUES (?, ?)
                ON CONFLICT(application_id) DO UPDATE SET
                    application_json = excluded.application_json,
                    updated_at = CURRENT_TIMESTAMP
                """,
                (application.id, payload),
            )
            connection.commit()
        return self.get(application.id)

    def get(self, application_id):
        with self.database.connect(readonly=True) as connection:
            row = connection.execute(
                "SELECT * FROM enrollment_workflows WHERE application_id = ?",
                (int(application_id),),
            ).fetchone()
        return self._state(row) if row else None

    def store_face(self, application_id, embedding, face_image):
        with self.database.connect() as connection:
            connection.execute(
                """
                UPDATE enrollment_workflows
                SET face_embedding = ?, face_image = ?, status = 'face_captured',
                    last_error = '', updated_at = CURRENT_TIMESTAMP
                WHERE application_id = ?
                """,
                (json.dumps(embedding), face_image, int(application_id)),
            )
            connection.commit()
        return self.get(application_id)

    def store_payment(self, application_id, amount, reference):
        with self.database.connect() as connection:
            connection.execute(
                """
                UPDATE enrollment_workflows
                SET paid_amount = ?, payment_reference = ?, status = 'paid',
                    last_error = '', updated_at = CURRENT_TIMESTAMP
                WHERE application_id = ?
                """,
                (int(amount), str(reference), int(application_id)),
            )
            connection.commit()
        return self.get(application_id)

    def biometric_payload(self, application_id):
        with self.database.connect(readonly=True) as connection:
            row = connection.execute(
                "SELECT face_embedding, face_image FROM enrollment_workflows WHERE application_id = ?",
                (int(application_id),),
            ).fetchone()
        if not row or not row["face_embedding"] or not row["face_image"]:
            return None
        return json.loads(row["face_embedding"]), row["face_image"]

    def mark_member_created(self, application_id, member_id):
        with self.database.connect() as connection:
            connection.execute(
                """
                UPDATE enrollment_workflows
                SET legacy_member_id = ?, status = 'member_created', updated_at = CURRENT_TIMESTAMP
                WHERE application_id = ?
                """,
                (int(member_id), int(application_id)),
            )
            connection.commit()
        return self.get(application_id)

    def mark_activated(self, application_id):
        with self.database.connect() as connection:
            connection.execute(
                """
                UPDATE enrollment_workflows
                SET status = 'activated', face_embedding = NULL, face_image = NULL,
                    last_error = '', updated_at = CURRENT_TIMESTAMP
                WHERE application_id = ?
                """,
                (int(application_id),),
            )
            connection.commit()
        return self.get(application_id)

    def mark_error(self, application_id, message):
        with self.database.connect() as connection:
            connection.execute(
                """
                UPDATE enrollment_workflows
                SET last_error = ?, updated_at = CURRENT_TIMESTAMP
                WHERE application_id = ?
                """,
                (str(message)[:1000], int(application_id)),
            )
            connection.commit()

