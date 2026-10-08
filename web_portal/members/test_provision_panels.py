import json
import tempfile
from io import StringIO
from pathlib import Path
from unittest.mock import patch

from django.core.management import call_command
from django.core.management.base import CommandError
from django.test import TransactionTestCase, override_settings
from django.utils import timezone

from .models import (
    CoachProfile, GymRemoteCommand, GymSyncCursor, GymSyncRecord,
    LegacyMember, MembershipApplication, Plan, User,
)


COMMAND = "provision_semi_private_panels"
MODULE = "members.management.commands.provision_semi_private_panels"


@override_settings(FITTRACK_REMOTE_SYNC=False,
                   PASSWORD_HASHERS=["django.contrib.auth.hashers.MD5PasswordHasher"])
class ProvisionPanelsTests(TransactionTestCase):
    def setUp(self):
        # The gym table is unmanaged, so Django's test flush does not empty it.
        LegacyMember.objects.all().delete()
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.plan = Plan.objects.create(name="نیمه‌خصوصی ۸ جلسه", gender="male", sessions_per_month=8)
        self.coach = User.objects.create_user(mobile="09129990000", password="OtherPass482!",
                                             first_name="امین", last_name="تهرانی",
                                             role="coach", status="active")
        self.profile = CoachProfile.objects.create(user=self.coach)
        self.member = self.gym_member("09121112233")

    def gym_member(self, mobile, **values):
        defaults = dict(first_name="عضو", last_name="آزمایشی", mobile=mobile,
                        national_id=None, gender="مرد", plan=self.plan.name,
                        used_sessions=3, debt=200, payment=800,
                        signup_time="1405-07-10 12:00:00", embedding="[0.2]", face_image=b"face")
        defaults.update(values)
        return LegacyMember.objects.create(**defaults)

    def audit(self, **options):
        out = StringIO()
        call_command(COMMAND, coach_name="امین تهرانی", stdout=out, **options)
        return json.loads(out.getvalue())

    def apply(self, fingerprint=None, **options):
        out = StringIO()
        fingerprint = fingerprint or self.audit(**options)["fingerprint"]
        with patch("sys.stdin", StringIO("Mramin123\n")):
            call_command(COMMAND, coach_name="امین تهرانی", apply=True,
                         expected_fingerprint=fingerprint, password_stdin=True,
                         backup_dir=Path(self.temp.name), stdout=out, **options)
        return json.loads(out.getvalue().splitlines()[-1])

    def test_audit_is_read_only_and_understands_plan_digits_and_spacing(self):
        self.member.plan = "نیمه خصوصی 8 جلسه"
        self.member.save()
        self.gym_member("09121112244", plan="بدنسازی ۸ جلسه")
        report = self.audit()
        self.assertEqual(report["members"], 1)
        self.assertEqual(report["issues"], [])
        self.assertEqual(User.objects.count(), 1)
        self.assertFalse(MembershipApplication.objects.exists())
        self.assertFalse(self.profile.allowed_plans.exists())

    def test_create_login_coach_access_backup_and_gym_data_preservation(self):
        before = list(LegacyMember.objects.values())
        command = GymRemoteCommand.objects.create(kind="member", local_id=self.member.pk, data={"debt": 1})
        result = self.apply()
        self.assertTrue(result["ok"])
        self.assertEqual(result["accounts_created"], 1)
        self.assertTrue(Path(result["backup"]).is_file())
        user = User.objects.get(mobile=self.member.mobile)
        self.assertNotEqual(user.password, "Mramin123")
        self.assertTrue(user.check_password("Mramin123"))
        self.assertEqual(user.membership_application.legacy_member_id, self.member.pk)
        self.assertEqual(user.membership_application.plan_id, self.plan.pk)
        self.assertEqual(user.membership_application.paid_amount, 800)
        self.assertEqual(list(LegacyMember.objects.values()), before)
        command.refresh_from_db()
        self.assertEqual(command.status, "pending")
        response = self.client.post("/api/login", data=json.dumps(dict(mobile=user.mobile, password="Mramin123")), content_type="application/json")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["user"]["fittrackMemberId"], self.member.pk)
        self.assertEqual(response.json()["user"]["sessionsUsed"], 3)
        self.client.force_login(self.coach)
        self.assertEqual(self.client.get("/api/coach/members").json()["members"][0]["id"], user.pk)

    def test_existing_account_and_application_are_reused_and_retry_is_idempotent(self):
        user = User.objects.create_user(mobile=self.member.mobile, password="PreviousPass482!", status="active")
        application = MembershipApplication.objects.create(user=user, plan=self.plan,
                                                            legacy_member_id=self.member.pk, status="active")
        self.apply()
        self.assertEqual(MembershipApplication.objects.get(user=user).pk, application.pk)
        user.refresh_from_db()
        encoded = user.password
        result = self.apply()
        user.refresh_from_db()
        self.assertEqual(User.objects.filter(mobile=user.mobile).count(), 1)
        self.assertEqual(user.password, encoded)
        self.assertEqual(result.get("accounts_created", 0), 0)
        self.assertEqual(result.get("existing_passwords_set", 0), 0)

    def test_duplicate_gym_mobile_blocks_entire_operation(self):
        self.gym_member(self.member.mobile, plan="بدنسازی ۱۲ جلسه")
        self.assertTrue(self.audit()["issues"])
        with self.assertRaises(CommandError):
            self.apply()
        self.assertEqual(User.objects.count(), 1)
        self.assertFalse(MembershipApplication.objects.exists())

    def test_explicitly_excluded_account_is_untouched(self):
        self.gym_member("۰۹۱۹۹۹۰۰۲۲۱")
        excluded = User.objects.create_user(mobile="09199900221", password="PreviousPass482!",
                                           role="admin", status="active", first_name="مدیر")
        before = User.objects.filter(pk=excluded.pk).values().get()
        report = self.audit(exclude_mobile=["09199900221"])
        self.assertEqual(report["members"], 1)
        self.assertEqual(report["excluded_gym_records"], 1)
        self.assertFalse(report["issues"])
        self.apply(exclude_mobile=["09199900221"])
        self.assertEqual(User.objects.filter(pk=excluded.pk).values().get(), before)
        self.assertFalse(MembershipApplication.objects.filter(user=excluded).exists())

    def test_ambiguous_plan_blocks_operation(self):
        Plan.objects.create(name=self.plan.name, gender="male", sessions_per_month=8)
        self.assertTrue(self.audit()["issues"])
        with self.assertRaises(CommandError):
            self.apply()

    def test_historical_plan_is_private_and_does_not_collide_with_gym_sync(self):
        old_name = self.plan.name
        self.member.plan = "نیمه خصوصی ۸ جلسه"
        self.member.save()
        self.plan.name = "نیمه خصوصی ۱۲ جلسه"
        self.plan.sessions_per_month = 12
        self.plan.save()
        self.assertTrue(self.audit()["issues"])
        report = self.audit(historical_sessions=[8])
        self.assertEqual(report["issues"], [])
        self.assertEqual(report["historical_plans_to_create"][0]["id"], -1)
        self.apply(historical_sessions=[8])
        historic = Plan.objects.get(pk=-1)
        self.assertFalse(historic.is_active)
        self.assertEqual(historic.sessions_per_month, 8)
        self.assertFalse(Plan.objects.filter(pk=historic.pk, is_active=True).exists())
        self.assertNotIn(historic.pk, [p["id"] for p in self.client.get("/api/plans").json()["plans"]])
        self.client.force_login(self.coach)
        members = self.client.get("/api/coach/members").json()["members"]
        self.assertEqual(len(members), 1)
        self.assertEqual(members[0]["plan"], self.member.plan)
        next_plan = Plan.objects.create(name=old_name, gender="male", sessions_per_month=8)
        self.assertGreater(next_plan.pk, 0)
        self.assertEqual(historic.pk, -1)

    def test_explicit_historical_access_uses_existing_archived_plan(self):
        self.plan.is_active = False
        self.plan.save()
        self.apply(historical_sessions=[8])
        self.assertEqual(Plan.objects.count(), 1)
        user = User.objects.get(mobile=self.member.mobile)
        self.assertEqual(user.membership_application.plan_id, self.plan.pk)
        self.client.force_login(self.coach)
        self.assertEqual(len(self.client.get("/api/coach/members").json()["members"]), 1)

    def test_cross_member_link_and_suspended_account_are_rejected(self):
        other = self.gym_member("09121112299", plan="بدنسازی ۱۲ جلسه")
        user = User.objects.create_user(mobile=self.member.mobile, password="OtherPass482!", status="suspended")
        MembershipApplication.objects.create(user=user, plan=self.plan, legacy_member_id=other.pk)
        self.assertGreaterEqual(len(self.audit()["issues"]), 2)
        with self.assertRaises(CommandError):
            self.apply()
        user.refresh_from_db()
        self.assertEqual(user.status, "suspended")
        self.assertTrue(user.check_password("OtherPass482!"))

    def test_changed_data_requires_new_review(self):
        fingerprint = self.audit()["fingerprint"]
        self.member.used_sessions += 1
        self.member.save()
        with self.assertRaises(CommandError):
            self.apply(fingerprint)
        self.assertFalse(MembershipApplication.objects.exists())

    def test_failed_authentication_rolls_back_all_changes(self):
        with patch(MODULE + ".authenticate", return_value=None):
            with self.assertRaises(CommandError):
                self.apply()
        self.assertEqual(User.objects.count(), 1)
        self.assertFalse(MembershipApplication.objects.exists())
        self.assertFalse(self.profile.allowed_plans.exists())

    @override_settings(FITTRACK_REMOTE_SYNC=True, FITTRACK_SYNC_SOURCE="test-gym")
    def test_remote_sync_evidence_is_required_and_face_flag_is_preserved(self):
        self.assertTrue(self.audit()["issues"])
        GymSyncCursor.objects.create(source="test-gym", sequence=1)
        GymSyncRecord.objects.create(kind="member", local_id=self.member.pk,
                                     data=dict(mobile=self.member.mobile, plan=self.member.plan, face_registered=False))
        self.assertEqual(self.audit()["issues"], [])
        self.apply()
        self.assertFalse(MembershipApplication.objects.get(user__mobile=self.member.mobile).face_registered)
        self.assertEqual(GymSyncCursor.objects.get().sequence, 1)

    @override_settings(FITTRACK_REMOTE_SYNC=True, FITTRACK_SYNC_SOURCE="test-gym")
    def test_old_sync_is_rejected(self):
        cursor = GymSyncCursor.objects.create(source="test-gym", sequence=1)
        GymSyncCursor.objects.filter(pk=cursor.pk).update(updated_at=timezone.now() - timezone.timedelta(days=2))
        self.assertTrue(any("too old" in issue for issue in self.audit()["issues"]))

    @override_settings(FITTRACK_REMOTE_SYNC=True, FITTRACK_SYNC_SOURCE="test-gym")
    def test_sync_heartbeat_and_unrelated_login_do_not_invalidate_review(self):
        cursor = GymSyncCursor.objects.create(source="test-gym", sequence=1)
        GymSyncRecord.objects.create(kind="member", local_id=self.member.pk,
                                     data=dict(mobile=self.member.mobile, plan=self.member.plan, face_registered=True))
        fingerprint = self.audit()["fingerprint"]
        GymSyncCursor.objects.filter(pk=cursor.pk).update(sequence=2)
        User.objects.filter(pk=self.coach.pk).update(last_login=timezone.now())
        self.assertEqual(self.audit()["fingerprint"], fingerprint)
        self.apply(fingerprint)
