import json
import base64

from django.conf import settings
from django.contrib.auth.hashers import check_password
from django.test import Client, TestCase

from .models import CoachProfile, LegacyMember, MembershipApplication, Plan, User, WorkoutProgram
from .hashers import LifeBoxLegacyPasswordHasher


class LegacyPasswordTests(TestCase):
    def test_pre_django_password_hash_is_accepted(self):
        salt = base64.urlsafe_b64encode(b"0123456789abcdef").decode()
        encoded = LifeBoxLegacyPasswordHasher().encode("StrongPass482!", salt, 310000)
        self.assertTrue(check_password("StrongPass482!", encoded))
        self.assertFalse(check_password("wrong-password", encoded))


class MembershipFlowTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        with cls.connection().cursor() as cursor:
            cursor.execute(
                """
                CREATE TABLE IF NOT EXISTS users (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    first_name TEXT NOT NULL, last_name TEXT NOT NULL, father_name TEXT,
                    national_id TEXT, certificate_no TEXT, address TEXT, mobile TEXT NOT NULL,
                    age INTEGER, gender TEXT NOT NULL, plan TEXT NOT NULL, embedding TEXT,
                    face_image BLOB, used_sessions INTEGER DEFAULT 0, signup_time TEXT NOT NULL,
                    debt INTEGER DEFAULT 0, payment INTEGER DEFAULT 0
                )
                """
            )
        cls.plan = Plan.objects.create(name="بدنسازی ۱۲ جلسه", gender=Plan.Gender.MALE, price=2400000, sessions_per_month=12)

    @classmethod
    def connection(cls):
        from django.db import connection

        return connection

    def signup(self, mobile="09121112233", national_id="0012345678"):
        return self.client.post(
            "/api/signup",
            data=json.dumps(
                {
                    "fullName": "کاربر آزمایشی",
                    "mobile": mobile,
                    "nationalId": national_id,
                    "address": "تهران، خیابان آزمایش",
                    "planId": self.plan.id,
                    "password": "StrongPass482!",
                },
                ensure_ascii=False,
            ),
            content_type="application/json",
        )

    def test_new_web_signup_stays_pending_until_fittrack_activation(self):
        response = self.signup()
        self.assertEqual(response.status_code, 201)
        self.assertEqual(response.json()["user"]["status"], User.Status.PENDING)
        application = MembershipApplication.objects.get(user__mobile="09121112233")

        desktop = Client(HTTP_AUTHORIZATION=f"Bearer {settings.FITTRACK_DESKTOP_API_TOKEN}")
        pending = desktop.get("/api/desktop/applications?mobile=09121112233")
        self.assertEqual(pending.status_code, 200)
        self.assertEqual(pending.json()["applications"][0]["id"], application.id)

        member = LegacyMember.objects.create(
            first_name="کاربر",
            last_name="آزمایشی",
            mobile="09121112233",
            gender="مرد",
            plan=self.plan.name,
            embedding="[0.1, 0.2]",
            face_image=b"face",
            signup_time="1405-05-20 12:00:00",
            payment=self.plan.price,
        )
        activated = desktop.post(
            f"/api/desktop/applications/{application.id}/activate",
            data=json.dumps({"legacyMemberId": member.id, "paidAmount": self.plan.price}),
            content_type="application/json",
        )
        self.assertEqual(activated.status_code, 200)
        application.refresh_from_db()
        self.assertEqual(application.status, MembershipApplication.Status.ACTIVE)
        self.assertEqual(application.user.status, User.Status.ACTIVE)

    def test_existing_fittrack_member_is_active_immediately(self):
        LegacyMember.objects.create(
            first_name="عضو",
            last_name="قدیمی",
            mobile="۰۹۱۲۲۲۲۳۳۴۴",
            gender="مرد",
            plan=self.plan.name,
            embedding="[0.2]",
            face_image=b"face",
            signup_time="1404-01-01 10:00:00",
        )
        response = self.signup(mobile="09122223344", national_id="0012345679")
        self.assertEqual(response.status_code, 201)
        self.assertEqual(response.json()["user"]["status"], User.Status.ACTIVE)

    def test_desktop_api_rejects_missing_token(self):
        response = self.client.get("/api/desktop/applications")
        self.assertEqual(response.status_code, 401)

    def test_desktop_activation_uses_bearer_token_without_browser_csrf(self):
        response = self.signup(mobile="09123334455", national_id="0012345680")
        application = MembershipApplication.objects.get(user__mobile="09123334455")
        member = LegacyMember.objects.create(
            first_name="تست",
            last_name="سی‌اس‌آر‌اف",
            mobile="09123334455",
            gender="مرد",
            plan=self.plan.name,
            embedding="[0.1, 0.2]",
            face_image=b"face",
            signup_time="1405-05-21 12:00:00",
            payment=self.plan.price,
        )
        strict_desktop = Client(
            enforce_csrf_checks=True,
            HTTP_AUTHORIZATION=f"Bearer {settings.FITTRACK_DESKTOP_API_TOKEN}",
        )
        activated = strict_desktop.post(
            f"/api/desktop/applications/{application.id}/activate",
            data=json.dumps({"legacyMemberId": member.id, "paidAmount": self.plan.price}),
            content_type="application/json",
        )
        self.assertEqual(activated.status_code, 200)


class CoachPanelFlowTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.plan = Plan.objects.create(
            name="بدنسازی ۱۲ جلسه مربی",
            gender=Plan.Gender.ALL,
            price=2_400_000,
            sessions_per_month=12,
        )
        cls.member = User.objects.create_user(
            mobile="09124445566",
            password="StrongMember482!",
            first_name="عضو",
            last_name="تمرینی",
            role=User.Role.MEMBER,
            status=User.Status.ACTIVE,
        )
        MembershipApplication.objects.create(
            user=cls.member,
            plan=cls.plan,
            status=MembershipApplication.Status.ACTIVE,
            legacy_member_id=321,
        )

    def test_fittrack_creates_coach_and_coach_manages_program_on_site(self):
        desktop = Client(HTTP_AUTHORIZATION=f"Bearer {settings.FITTRACK_DESKTOP_API_TOKEN}")
        created = desktop.post(
            "/api/desktop/coaches",
            data=json.dumps({
                "mobile": "09127778899",
                "password": "StrongCoach482!",
                "planIds": [self.plan.id],
            }),
            content_type="application/json",
        )
        self.assertEqual(created.status_code, 201)
        coach = User.objects.get(mobile="09127778899")
        self.assertEqual(coach.role, User.Role.COACH)
        self.assertEqual(list(coach.coach_profile.allowed_plans.all()), [self.plan])

        coach_client = Client()
        self.assertTrue(coach_client.login(mobile=coach.mobile, password="StrongCoach482!"))
        profile = coach_client.patch(
            "/api/coach/profile",
            data=json.dumps({
                "fullName": "مربی آزمایشی",
                "specialty": "افزایش قدرت",
                "bio": "مربی رسمی لایف‌باکس",
            }, ensure_ascii=False),
            content_type="application/json",
        )
        self.assertEqual(profile.status_code, 200)
        members = coach_client.get("/api/coach/members")
        self.assertEqual(members.json()["members"][0]["id"], self.member.id)

        program = coach_client.post(
            "/api/coach/programs",
            data=json.dumps({
                "memberId": self.member.id,
                "title": "ماه اول",
                "durationWeeks": 4,
                "days": [
                    {
                        "weekday": "saturday",
                        "movements": [
                            "اسکوات — ۳ ست × ۱۲ تکرار",
                            "پرس پا — ۳ ست × ۱۰ تکرار",
                            "لانج — ۳ ست × ۱۲ تکرار",
                        ],
                    },
                    {
                        "weekday": "monday",
                        "movements": ["پرس سینه — ۴ ست × ۱۰ تکرار"],
                    },
                    {
                        "weekday": "wednesday",
                        "movements": ["ددلیفت — ۳ ست × ۸ تکرار"],
                    },
                ],
            }, ensure_ascii=False),
            content_type="application/json",
        )
        self.assertEqual(program.status_code, 200)
        self.assertEqual(WorkoutProgram.objects.count(), 1)
        saved_program = WorkoutProgram.objects.get()
        self.assertEqual(saved_program.duration_weeks, 4)
        self.assertEqual(saved_program.schedule_json[0]["label"], "شنبه")
        self.assertEqual(len(saved_program.schedule_json), 3)

        member_client = Client()
        member_client.force_login(self.member)
        member_program = member_client.get("/api/member/program")
        self.assertEqual(member_program.status_code, 200)
        self.assertEqual(member_program.json()["program"]["title"], "ماه اول")
        self.assertEqual(member_program.json()["program"]["durationWeeks"], 4)
        self.assertEqual(member_program.json()["program"]["days"][1]["label"], "دوشنبه")

    def test_weekly_program_rejects_duplicate_weekdays(self):
        coach = User.objects.create_user(
            mobile="09127770001",
            password="StrongCoach482!",
            role=User.Role.COACH,
            status=User.Status.ACTIVE,
        )
        profile = CoachProfile.objects.create(user=coach)
        profile.allowed_plans.add(self.plan)
        self.client.force_login(coach)
        response = self.client.post(
            "/api/coach/programs",
            data=json.dumps({
                "memberId": self.member.id,
                "title": "برنامه تکراری",
                "durationWeeks": 4,
                "days": [
                    {"weekday": "saturday", "movements": ["اسکوات"]},
                    {"weekday": "saturday", "movements": ["پرس پا"]},
                ],
            }, ensure_ascii=False),
            content_type="application/json",
        )
        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.json()["field"], "trainingDays")
        self.assertEqual(WorkoutProgram.objects.count(), 0)

    def test_member_cannot_access_coach_api(self):
        self.client.force_login(self.member)
        response = self.client.get("/api/coach/programs")
        self.assertEqual(response.status_code, 403)

    def test_fittrack_can_reset_linked_member_password_without_reading_old_password(self):
        desktop = Client(HTTP_AUTHORIZATION=f"Bearer {settings.FITTRACK_DESKTOP_API_TOKEN}")
        response = desktop.patch(
            "/api/desktop/members/321/password",
            data=json.dumps({"password": "NewMemberPass482!"}),
            content_type="application/json",
        )
        self.assertEqual(response.status_code, 200)
        self.member.refresh_from_db()
        self.assertTrue(self.member.check_password("NewMemberPass482!"))
        self.assertNotIn("password", response.json())

    def test_password_reset_reports_member_without_connected_site_account(self):
        desktop = Client(HTTP_AUTHORIZATION=f"Bearer {settings.FITTRACK_DESKTOP_API_TOKEN}")
        response = desktop.patch(
            "/api/desktop/members/999/password",
            data=json.dumps({"password": "NewMemberPass482!"}),
            content_type="application/json",
        )
        self.assertEqual(response.status_code, 404)

    def test_life_box_admin_can_create_and_edit_membership_plans(self):
        desktop = Client(HTTP_AUTHORIZATION=f"Bearer {settings.FITTRACK_DESKTOP_API_TOKEN}")
        created = desktop.post(
            "/api/desktop/plans",
            data=json.dumps({
                "name": "پلن تست مدیریت",
                "gender": "female",
                "price": 3_100_000,
                "sessionsPerMonth": 14,
                "isActive": True,
            }, ensure_ascii=False),
            content_type="application/json",
        )
        self.assertEqual(created.status_code, 201)
        plan_id = created.json()["plan"]["id"]
        updated = desktop.patch(
            f"/api/desktop/plans/{plan_id}",
            data=json.dumps({"price": 3_300_000, "isActive": False}),
            content_type="application/json",
        )
        self.assertEqual(updated.status_code, 200)
        self.assertEqual(updated.json()["plan"]["price"], 3_300_000)
        self.assertFalse(updated.json()["plan"]["isActive"])
        self.assertFalse(Plan.objects.get(pk=plan_id).is_active)

# Create your tests here.
