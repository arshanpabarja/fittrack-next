import sqlite3
import tempfile
import unittest
from contextlib import closing
from datetime import datetime
from pathlib import Path

from app.data.attendance import AttendanceRepository
from app.data.members import MembersRepository
from app.data.memberships import MembershipRepository
from app.domain.errors import FitTrackError
from app.domain.dates import normalize_membership_datetime
from app.services.attendance import AttendanceService
from app.services.face_index import FaceIndex
from tests.test_repositories import MEMBERS_SCHEMA


class StubAccessController:
    def __init__(self):
        self.events = []

    def open_entry(self, locker_id):
        self.events.append(("entry", locker_id))

    def open_exit(self):
        self.events.append(("exit", None))


class AttendanceTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(ignore_cleanup_errors=True)
        root = Path(self.temp.name)
        members_path = root / "members.db"
        with closing(sqlite3.connect(members_path)) as connection:
            connection.execute(MEMBERS_SCHEMA)
            connection.executemany(
                """
                INSERT INTO users (
                    first_name, last_name, mobile, gender, plan, embedding,
                    signup_time, used_sessions
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                [
                    ("آرش", "احمدی", "09120000001", "مرد", "بدنسازی", "[1, 0]", "2026-01-01", 0),
                    ("سام", "کریمی", "09120000002", "مرد", "کلیس", "[0, 1]", "2026-01-01", 4),
                ],
            )
            connection.commit()
        self.members_path = members_path
        self.members = MembersRepository(members_path)
        self.attendance = AttendanceRepository(root / "state.db", locker_count=2)
        self.memberships = MembershipRepository(root / "state.db")
        self.access = StubAccessController()
        self.service = AttendanceService(
            FaceIndex(self.members, threshold=0.5),
            self.attendance,
            self.members,
            self.access,
            self.memberships,
        )

    def tearDown(self):
        self.temp.cleanup()

    def test_check_in_and_out_are_atomic_and_update_usage(self):
        check_in = self.service.check_in([0.99, 0.01])
        self.assertEqual(check_in.member.mobile, "09120000001")
        self.assertEqual(check_in.member.signup_time, "2026-01-01")
        self.assertEqual(check_in.locker_id, 1)
        self.assertEqual(self.attendance.summary(), {"inside": 1, "free_lockers": 1})
        self.assertEqual(self.members.get(1).used_sessions, 1)
        self.assertEqual(self.access.events, [("entry", 1)])

        check_out = self.service.check_out([1, 0])
        self.assertEqual(check_out.locker_id, 1)
        self.assertEqual(self.attendance.summary(), {"inside": 0, "free_lockers": 2})
        self.assertEqual(self.access.events[-1], ("exit", None))

    def test_admin_activity_overview_supports_today_and_month(self):
        member = self.service.face_index.match([1, 0])
        self.attendance.check_in(member, "2026-08-12 10:00:00")
        self.attendance.check_out(member.mobile, "2026-08-12 11:00:00")
        self.attendance.check_in(member, "2026-08-10 10:00:00")
        overview = self.attendance.activity_overview(
            "2026-08-12", "2026-08", period="month"
        )
        self.assertEqual(overview["today_entries"], 1)
        self.assertEqual(overview["month_entries"], 2)
        self.assertEqual(overview["inside"], 1)
        self.assertEqual(len(overview["items"]), 2)

    def test_duplicate_active_check_in_is_rejected(self):
        self.service.check_in([1, 0])
        with self.assertRaises(FitTrackError):
            self.service.check_in([1, 0])
        self.assertEqual(self.attendance.summary()["inside"], 1)

    def test_unknown_face_is_rejected(self):
        with self.assertRaises(FitTrackError):
            self.service.check_in([-1, 0])
        self.assertEqual(self.attendance.summary()["inside"], 0)

    def test_reports_are_paginated_without_legacy_database_scan(self):
        self.service.check_in([1, 0])
        self.service.check_out([1, 0])
        page = self.attendance.list_sessions(search="09120000001", page=1, page_size=10)
        self.assertEqual(len(page.items), 1)
        self.assertFalse(page.has_next)
        self.assertTrue(page.items[0].checked_out_at)

    def test_members_are_automatically_checked_out_after_sixty_minutes(self):
        member = self.service.face_index.match([1, 0])
        self.attendance.check_in(member, "2026-08-12 10:00:00")
        count = self.attendance.auto_checkout(
            minutes=60,
            now=datetime(2026, 8, 12, 11, 0, 1),
        )
        self.assertEqual(count, 1)
        self.assertEqual(self.attendance.summary(), {"inside": 0, "free_lockers": 2})

    def test_first_grace_visit_is_negative_and_stores_its_date(self):
        with closing(sqlite3.connect(self.members_path)) as connection:
            connection.execute(
                "UPDATE users SET plan = ?, used_sessions = 12 WHERE id = 1",
                ("بدنسازی ۱۲ جلسه در ماه",),
            )
            connection.commit()
        result = self.service.check_in([1, 0])
        self.assertEqual(result.member.remaining_sessions, -1)
        self.assertEqual(self.members.get(1).used_sessions, 13)
        self.assertEqual(
            self.memberships.grace_started_at(1),
            normalize_membership_datetime(result.occurred_at),
        )

    def test_entry_after_five_grace_visits_is_blocked(self):
        with closing(sqlite3.connect(self.members_path)) as connection:
            connection.execute(
                "UPDATE users SET plan = ?, used_sessions = 17 WHERE id = 1",
                ("بدنسازی ۱۲ جلسه در ماه",),
            )
            connection.commit()
        with self.assertRaisesRegex(FitTrackError, "پنج جلسه مهلت"):
            self.service.check_in([1, 0])
        self.assertEqual(self.attendance.summary()["inside"], 0)
        self.assertEqual(self.members.get(1).used_sessions, 17)


if __name__ == "__main__":
    unittest.main()
