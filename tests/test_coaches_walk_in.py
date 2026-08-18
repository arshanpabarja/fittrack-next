import json
import sqlite3
import tempfile
import unittest
from contextlib import closing
from pathlib import Path

from app.data.members import MembersRepository
from app.domain.models import CoachAccount, PaymentReceipt, SignupPlan
from app.services.coaches import CoachesService
from app.services.members import MemberService
from app.services.walk_in import WalkInSignupService
from tests.test_repositories import MEMBERS_SCHEMA


class SuccessfulPos:
    def charge(self, amount):
        return PaymentReceipt(True, int(amount), "TEST-WALK-IN", "موفق")


class CoachesAndWalkInTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(ignore_cleanup_errors=True)
        self.root = Path(self.temp.name)
        self.members_path = self.root / "members.db"
        with closing(sqlite3.connect(self.members_path)) as connection:
            connection.execute(MEMBERS_SCHEMA)
            connection.execute(
                """
                INSERT INTO users (
                    first_name, last_name, national_id, mobile, gender,
                    plan, signup_time, used_sessions
                ) VALUES (?, ?, ?, ?, ?, ?, ?, 0)
                """,
                (
                    "آرشان", "احمدی", "0012345678", "09120000001", "مرد",
                    "بدنسازی ۱۲ جلسه در ماه", "2026-08-18 10:00:00",
                ),
            )
            connection.commit()
        self.members = MembersRepository(self.members_path)

    def tearDown(self):
        self.temp.cleanup()

    def test_fittrack_only_sends_coach_credentials_and_plan_access(self):
        class CoachApi:
            def __init__(self):
                self.saved = None

            def list_plans(self):
                return (SignupPlan(8, "بدنسازی ۱۲ جلسه", 2_400_000),)

            def list_coaches(self):
                return ()

            def save_coach(self, **values):
                self.saved = values
                return CoachAccount(
                    3, values["mobile"], "", "", tuple(values["plan_ids"]),
                    ("بدنسازی ۱۲ جلسه",), False,
                )

        api = CoachApi()
        service = CoachesService(api)
        coach = service.save_coach({
            "mobile": "09121112233",
            "password": "StrongCoach482!",
            "plan_ids": [8],
        })
        self.assertEqual(coach.mobile, "09121112233")
        self.assertEqual(api.saved["plan_ids"], [8])
        self.assertNotIn("specialty", api.saved)

    def test_walk_in_signup_creates_paid_member(self):
        plans_path = self.root / "plans.json"
        plans_path.write_text(
            json.dumps({
                "مرد": [{
                    "name": "بدنسازی ۱۲ جلسه در ماه",
                    "price": "۲,۴۰۰,۰۰۰ تومان",
                }],
                "زن": [],
            }, ensure_ascii=False),
            encoding="utf-8",
        )
        service = WalkInSignupService(plans_path, self.members, SuccessfulPos())
        plan = service.list_plans()[0]
        result = service.register(
            {
                "full_name": "سام کریمی",
                "mobile": "09123334455",
                "national_id": "0098765432",
                "father_name": "علی",
                "certificate_no": "2",
                "age": 28,
                "gender": "مرد",
                "address": "تهران، خیابان آزادی",
            },
            plan,
            [1.0, 0.0],
            b"face-image",
        )
        member = self.members.get(result.member_id)
        self.assertEqual(plan.price, 2_400_000)
        self.assertEqual(member.full_name, "سام کریمی")
        self.assertEqual(member.payment, 2_400_000)
        self.assertEqual(member.used_sessions, 0)

    def test_member_service_resets_site_password_through_django_api(self):
        class PasswordApi:
            def __init__(self):
                self.call = None

            def reset_member_password(self, member_id, password):
                self.call = (member_id, password)
                return {"ok": True, "mobile": "09120000001"}

        api = PasswordApi()
        service = MemberService(self.members, api=api)
        result = service.reset_site_password(1, "NewPass482!", "NewPass482!")
        self.assertEqual(api.call, (1, "NewPass482!"))
        self.assertEqual(result["mobile"], "09120000001")


if __name__ == "__main__":
    unittest.main()
