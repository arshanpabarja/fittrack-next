import hashlib
import sqlite3
import tempfile
import unittest
from contextlib import closing
from pathlib import Path

from app.data.manager import ManagerRepository
from app.data.members import MembersRepository
from app.data.memberships import MembershipRepository
from app.domain.models import PaymentReceipt
from app.domain.membership import remaining_sessions, session_allowance
from app.services.auth import AuthService
from app.services.members import MemberService
from app.domain.errors import ValidationError


MEMBERS_SCHEMA = """
CREATE TABLE users (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    first_name TEXT NOT NULL,
    last_name TEXT NOT NULL,
    father_name TEXT,
    national_id TEXT,
    certificate_no TEXT,
    address TEXT,
    mobile TEXT NOT NULL,
    age INTEGER,
    gender TEXT NOT NULL,
    plan TEXT NOT NULL,
    embedding TEXT,
    face_image BLOB,
    used_sessions INTEGER DEFAULT 0,
    signup_time TEXT NOT NULL,
    debt INTEGER DEFAULT 0,
    payment INTEGER DEFAULT 0
)
"""


class RepositoryTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        root = Path(self.temp.name)
        self.members_path = root / "members.db"
        self.manager_path = root / "manager.db"
        with closing(sqlite3.connect(self.members_path)) as connection:
            connection.execute(MEMBERS_SCHEMA)
            connection.executemany(
                """
                INSERT INTO users (
                    first_name, last_name, father_name, national_id,
                    certificate_no, address, mobile, age, gender, plan,
                    embedding, face_image, used_sessions, signup_time,
                    debt, payment
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                [
                    ("آرش", "احمدی", "رضا", "0012345678", "1", "تهران", "09120000001", 25, "مرد", "بدنسازی", "[1,2]", b"face-a", 3, "2026-01-01", 0, 100),
                    ("سام", "کریمی", "علی", "0012345679", "2", "تهران", "09120000002", 29, "مرد", "کلیس", "[3,4]", b"face-b", 5, "2026-01-02", 250, 200),
                ],
            )
            connection.commit()
        with closing(sqlite3.connect(self.manager_path)) as connection:
            connection.execute(
                "CREATE TABLE manager_credentials (id INTEGER PRIMARY KEY, username TEXT, password_hash TEXT)"
            )
            connection.execute(
                "INSERT INTO manager_credentials (username, password_hash) VALUES (?, ?)",
                ("admin", hashlib.sha256(b"secret").hexdigest()),
            )
            connection.commit()

    def tearDown(self):
        self.temp.cleanup()

    def test_members_are_paginated_and_searchable(self):
        repository = MembersRepository(self.members_path)
        page = repository.list_page(search="09120000002", page=1, page_size=10)
        self.assertEqual(len(page.items), 1)
        self.assertEqual(page.items[0].last_name, "کریمی")
        self.assertFalse(page.has_next)

    def test_member_update_preserves_biometric_data(self):
        service = MemberService(MembersRepository(self.members_path))
        service.update_member(1, {
            "first_name": "آرش",
            "last_name": "احمدی‌پور",
            "mobile": "۰۹۱۲۰۰۰۰۰۰۱",
            "national_id": "0012345678",
            "plan": "بدنسازی",
            "debt": 0,
            "payment": 100,
        })
        with closing(sqlite3.connect(self.members_path)) as connection:
            row = connection.execute(
                "SELECT last_name, mobile, embedding, face_image FROM users WHERE id = 1"
            ).fetchone()
        self.assertEqual(row[0], "احمدی‌پور")
        self.assertEqual(row[1], "09120000001")
        self.assertEqual(row[2], "[1,2]")
        self.assertEqual(row[3], b"face-a")

    def test_invalid_mobile_is_rejected_before_database_write(self):
        service = MemberService(MembersRepository(self.members_path))
        with self.assertRaises(ValidationError):
            service.update_member(1, {
                "first_name": "آرش",
                "last_name": "احمدی",
                "mobile": "123",
                "national_id": "0012345678",
            })

    def _edit_values(self, **changes):
        return {"first_name": "آرش", "last_name": "احمدی", "mobile": "09120000001",
                "national_id": "0012345678", "plan": "بدنسازی ۱۲ جلسه در ماه", **changes}

    def test_edit_registration_date_and_remaining_sessions(self):
        repository = MembersRepository(self.members_path)
        service = MemberService(repository)
        updated = service.update_member(1, self._edit_values(
            signup_time="۱۴۰۵/۰۶/۳۰ ۰۹:۱۵", remaining_sessions="۷"))
        self.assertEqual(updated.signup_time, "1405-06-30 09:15:00")
        self.assertEqual(updated.used_sessions, 5)
        self.assertEqual(updated.remaining_sessions, 7)
        repository.increment_used_sessions(1)
        self.assertEqual(repository.get(1).remaining_sessions, 6)
        with closing(sqlite3.connect(self.members_path)) as connection:
            row = connection.execute("SELECT embedding, face_image, payment FROM users WHERE id = 1").fetchone()
        self.assertEqual(row, ("[1,2]", b"face-a", 100))

    def test_negative_remaining_sessions_and_correction_clear_old_grace(self):
        repository = MembersRepository(self.members_path)
        memberships = MembershipRepository(Path(self.temp.name) / "state.db")
        service = MemberService(repository, memberships)
        memberships.begin_grace(1, "1405-06-20")
        updated = service.update_member(1, self._edit_values(remaining_sessions=-3))
        self.assertEqual(updated.used_sessions, 15)
        self.assertTrue(updated.renewal_required)
        self.assertIsNotNone(memberships.grace_started_at(1))
        updated = service.update_member(1, self._edit_values(remaining_sessions=5))
        self.assertEqual(updated.remaining_sessions, 5)
        self.assertIsNone(memberships.grace_started_at(1))

    def test_invalid_membership_edits_leave_member_unchanged(self):
        repository = MembersRepository(self.members_path)
        service = MemberService(repository)
        original = repository.get(1)
        for changes in [
            {"signup_time": ""}, {"signup_time": "1405/07/31"},
            {"signup_time": "1405/13/01"}, {"signup_time": "1405/06/30 25:00"},
            {"remaining_sessions": 13}, {"remaining_sessions": 1.5},
            {"plan": "بدنسازی", "remaining_sessions": 5},
        ]:
            with self.subTest(changes=changes), self.assertRaises(ValidationError):
                service.update_member(1, self._edit_values(**changes))
            self.assertEqual(repository.get(1), original)

    def test_profile_edit_preserves_date_and_sessions_when_omitted(self):
        repository = MembersRepository(self.members_path)
        updated = MemberService(repository).update_member(1, self._edit_values())
        self.assertEqual(updated.signup_time, "2026-01-01")
        self.assertEqual(updated.used_sessions, 3)

    def test_manager_password_is_verified_with_legacy_hash(self):
        service = AuthService(ManagerRepository(self.manager_path))
        self.assertEqual(service.login("admin", "secret"), "admin")
        with self.assertRaises(ValidationError):
            service.login("admin", "wrong")

    def test_delete_archives_member_before_removal(self):
        repository = MembersRepository(self.members_path)
        deleted = repository.delete(1)
        self.assertEqual(deleted["mobile"], "09120000001")
        with closing(sqlite3.connect(self.members_path)) as connection:
            remaining = connection.execute("SELECT COUNT(*) FROM users WHERE id = 1").fetchone()[0]
            archive = connection.execute(
                "SELECT original_id, face_image, embedding FROM fittrack_deleted_members_archive"
            ).fetchone()
        self.assertEqual(remaining, 0)
        self.assertEqual(archive, (1, b"face-a", "[1,2]"))

    def test_session_allowance_supports_persian_and_latin_digits(self):
        self.assertEqual(session_allowance("بدنسازی ۱۲ جلسه در ماه"), 12)
        self.assertEqual(session_allowance("بدنسازی 24 جلسه ای ۲۴ جلسه در ماه"), 24)
        self.assertEqual(remaining_sessions("بدنسازی ۱۲ جلسه در ماه", 15), -3)

    def test_renewal_carries_grace_sessions_into_the_new_plan(self):
        class SuccessfulPos:
            def charge(self, amount):
                return PaymentReceipt(True, amount, "TEST-RENEW", "موفق")

        repository = MembersRepository(self.members_path)
        with closing(sqlite3.connect(self.members_path)) as connection:
            connection.execute(
                "UPDATE users SET plan = ?, used_sessions = 15 WHERE id = 1",
                ("بدنسازی ۱۲ جلسه در ماه",),
            )
            connection.commit()
        memberships = MembershipRepository(Path(self.temp.name) / "state.db")
        memberships.begin_grace(1, "2026-08-10 09:15:00")
        service = MemberService(repository, memberships, SuccessfulPos())

        result = service.renew_member(
            1,
            "بدنسازی ۱۲ جلسه در ماه",
            2_800_000,
        )

        self.assertEqual(result.carried_sessions, 3)
        self.assertEqual(result.member.used_sessions, 3)
        self.assertEqual(result.member.remaining_sessions, 9)
        self.assertEqual(result.member.signup_time, "1405-05-19 09:15:00")
        self.assertIsNone(memberships.grace_started_at(1))
        self.assertEqual(len(memberships.renewal_history(1)), 1)


if __name__ == "__main__":
    unittest.main()
