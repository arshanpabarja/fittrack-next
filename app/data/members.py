from app.data.sqlite import SqliteDatabase
from app.domain.dates import jalali_now, normalize_membership_datetime
from app.domain.errors import RecordNotFound
from datetime import datetime
import json
from app.domain.models import MemberDetails, MemberPage, MemberSummary


SUMMARY_COLUMNS = """
    id, first_name, last_name, mobile, national_id, plan,
    COALESCE(used_sessions, 0) AS used_sessions,
    COALESCE(debt, 0) AS debt,
    signup_time
"""


class MembersRepository:
    def __init__(self, database_path):
        self.database = SqliteDatabase(database_path)

    @staticmethod
    def _summary(row):
        return MemberSummary(
            id=row["id"],
            first_name=row["first_name"] or "",
            last_name=row["last_name"] or "",
            mobile=row["mobile"] or "",
            national_id=row["national_id"] or "",
            plan=row["plan"] or "",
            used_sessions=row["used_sessions"] or 0,
            debt=row["debt"] or 0,
            signup_time=row["signup_time"] or "",
        )

    def list_page(self, *, search="", page=1, page_size=40):
        page = max(1, int(page))
        page_size = min(100, max(10, int(page_size)))
        query = search.strip()
        parameters = []
        where = ""
        if query:
            where = """
                WHERE first_name LIKE ? OR last_name LIKE ?
                   OR mobile LIKE ? OR national_id LIKE ?
            """
            token = f"%{query}%"
            parameters.extend([token, token, token, token])
        parameters.extend([page_size + 1, (page - 1) * page_size])
        sql = f"""
            SELECT {SUMMARY_COLUMNS}
            FROM users
            {where}
            ORDER BY id DESC
            LIMIT ? OFFSET ?
        """
        with self.database.connect(readonly=True) as connection:
            rows = connection.execute(sql, parameters).fetchall()
        items = tuple(self._summary(row) for row in rows[:page_size])
        return MemberPage(items, page, page_size, len(rows) > page_size)

    def get(self, member_id):
        sql = f"""
            SELECT {SUMMARY_COLUMNS}, father_name, certificate_no, address,
                   age, gender, COALESCE(payment, 0) AS payment
            FROM users WHERE id = ?
        """
        with self.database.connect(readonly=True) as connection:
            row = connection.execute(sql, (int(member_id),)).fetchone()
        if not row:
            raise RecordNotFound("عضو موردنظر پیدا نشد.")
        base = self._summary(row)
        return MemberDetails(
            **base.__dict__,
            father_name=row["father_name"] or "",
            certificate_no=row["certificate_no"] or "",
            address=row["address"] or "",
            age=row["age"],
            gender=row["gender"] or "",
            payment=row["payment"] or 0,
        )

    def update(self, member_id, values):
        allowed = {
            "first_name", "last_name", "father_name", "national_id",
            "certificate_no", "address", "mobile", "age", "gender",
            "plan", "debt", "payment",
        }
        payload = {key: value for key, value in values.items() if key in allowed}
        if not payload:
            return self.get(member_id)
        assignments = ", ".join(f"{key} = ?" for key in payload)
        parameters = [*payload.values(), int(member_id)]
        with self.database.connect() as connection:
            cursor = connection.execute(
                f"UPDATE users SET {assignments} WHERE id = ?", parameters
            )
            if cursor.rowcount != 1:
                raise RecordNotFound("عضو موردنظر پیدا نشد.")
            connection.commit()
        return self.get(member_id)

    def find_id_by_mobile(self, mobile):
        with self.database.connect(readonly=True) as connection:
            row = connection.execute(
                "SELECT id FROM users WHERE mobile = ? ORDER BY id DESC LIMIT 1",
                (str(mobile),),
            ).fetchone()
        return int(row["id"]) if row else None

    def find_id_by_national_id(self, national_id):
        with self.database.connect(readonly=True) as connection:
            row = connection.execute(
                "SELECT id FROM users WHERE national_id = ? ORDER BY id DESC LIMIT 1",
                (str(national_id),),
            ).fetchone()
        return int(row["id"]) if row else None

    def create_walk_in(self, values, embedding, face_image, paid_amount):
        payload = (
            values["first_name"], values["last_name"], values.get("father_name", ""),
            values.get("national_id", ""), values.get("certificate_no", ""),
            values.get("address", ""), values["mobile"], values.get("age"),
            values.get("gender", "مرد"), values["plan"], json.dumps(embedding),
            face_image, jalali_now(),
            int(paid_amount),
        )
        with self.database.connect() as connection:
            cursor = connection.execute(
                """
                INSERT INTO users (
                    first_name, last_name, father_name, national_id,
                    certificate_no, address, mobile, age, gender, plan,
                    embedding, face_image, signup_time, debt, payment, used_sessions
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 0, ?, 0)
                """,
                payload,
            )
            member_id = int(cursor.lastrowid)
            connection.commit()
        return member_id

    def create_from_application(
        self,
        application,
        details,
        embedding,
        face_image,
        paid_amount,
    ):
        existing = self.find_id_by_mobile(application.mobile)
        if existing:
            return existing
        gender = details.get("gender") or {
            "male": "مرد",
            "female": "زن",
        }.get(application.gender, "مرد")
        values = (
            application.first_name,
            application.last_name,
            details.get("father_name", ""),
            application.national_id,
            details.get("certificate_no", ""),
            application.address,
            application.mobile,
            details.get("age"),
            gender,
            application.plan,
            json.dumps(embedding),
            face_image,
            jalali_now(),
            max(0, int(application.price) - int(paid_amount)),
            int(paid_amount),
        )
        with self.database.connect() as connection:
            cursor = connection.execute(
                """
                INSERT INTO users (
                    first_name, last_name, father_name, national_id,
                    certificate_no, address, mobile, age, gender, plan,
                    embedding, face_image, signup_time, debt, payment
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                values,
            )
            member_id = int(cursor.lastrowid)
            connection.commit()
        return member_id

    def face_records(self):
        with self.database.connect(readonly=True) as connection:
            return connection.execute(
                """
                SELECT id, first_name, last_name, mobile, plan,
                       COALESCE(used_sessions, 0) AS used_sessions, embedding
                FROM users
                WHERE embedding IS NOT NULL AND embedding != ''
                """
            ).fetchall()

    def increment_used_sessions(self, member_id):
        with self.database.connect() as connection:
            cursor = connection.execute(
                """
                UPDATE users
                SET used_sessions = COALESCE(used_sessions, 0) + 1
                WHERE id = ?
                """,
                (int(member_id),),
            )
            if cursor.rowcount != 1:
                raise RecordNotFound("عضو موردنظر برای ثبت جلسه پیدا نشد.")
            connection.commit()

    def renew_membership(
        self,
        member_id,
        *,
        plan,
        carried_sessions,
        signup_time,
        paid_amount,
    ):
        with self.database.connect() as connection:
            cursor = connection.execute(
                """
                UPDATE users
                SET plan = ?, used_sessions = ?, signup_time = ?,
                    payment = ?, debt = 0
                WHERE id = ?
                """,
                (
                    str(plan),
                    int(carried_sessions),
                    normalize_membership_datetime(signup_time),
                    int(paid_amount),
                    int(member_id),
                ),
            )
            if cursor.rowcount != 1:
                raise RecordNotFound("عضو موردنظر برای تمدید پیدا نشد.")
            connection.commit()
        return self.get(member_id)

    def delete(self, member_id):
        member_id = int(member_id)
        with self.database.connect() as connection:
            connection.execute("BEGIN IMMEDIATE")
            row = connection.execute(
                "SELECT * FROM users WHERE id = ?", (member_id,)
            ).fetchone()
            if not row:
                raise RecordNotFound("عضو موردنظر پیدا نشد.")
            connection.execute(
                """
                CREATE TABLE IF NOT EXISTS fittrack_deleted_members_archive (
                    archive_id INTEGER PRIMARY KEY AUTOINCREMENT,
                    original_id INTEGER NOT NULL,
                    member_json TEXT NOT NULL,
                    face_image BLOB,
                    embedding TEXT,
                    deleted_at TEXT NOT NULL
                )
                """
            )
            payload = {
                key: row[key]
                for key in row.keys()
                if key not in {"face_image", "embedding"}
            }
            connection.execute(
                """
                INSERT INTO fittrack_deleted_members_archive (
                    original_id, member_json, face_image, embedding, deleted_at
                ) VALUES (?, ?, ?, ?, ?)
                """,
                (
                    member_id,
                    json.dumps(payload, ensure_ascii=False),
                    row["face_image"],
                    row["embedding"],
                    datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                ),
            )
            connection.execute("DELETE FROM users WHERE id = ?", (member_id,))
            connection.commit()
        return payload
