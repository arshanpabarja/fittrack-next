import json
from datetime import timedelta
from unittest.mock import MagicMock, patch

from django.core.cache import cache
from django.test import Client, TestCase, override_settings
from django.utils import timezone

from .models import PasswordResetChallenge, SignupOTP, User
from .password_reset import reset_digest
from .views import signup_otp_digest


@override_settings(PASSWORD_RESET_RESEND_SECONDS=60, PASSWORD_RESET_OTP_TTL_SECONDS=180,
                   PASSWORD_RESET_TOKEN_TTL_SECONDS=300, PASSWORD_RESET_MAX_SENDS_PER_HOUR=5,
                   PASSWORD_RESET_MAX_ATTEMPTS=5, PASSWORD_RESET_MAX_IP_SENDS_PER_HOUR=20)
class PasswordResetTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.user = User.objects.create_user(mobile="09121112233", password="OriginalPass482!",
                                           status=User.Status.ACTIVE)

    def setUp(self):
        cache.clear()
        self.sender = patch("members.password_reset._send_otp_sms").start()
        patch("members.password_reset.secrets.randbelow", return_value=2345).start()
        self.addCleanup(patch.stopall)

    def post(self, action, payload, client=None):
        return (client or self.client).post(f"/api/password-reset/{action}",
                                           json.dumps(payload), content_type="application/json")

    def send(self, mobile=None):
        return self.post("send", {"mobile": mobile or self.user.mobile})

    def verify(self, code="12345", mobile=None):
        return self.post("verify", {"mobile": mobile or self.user.mobile, "otpCode": code})

    def grant(self):
        self.assertEqual(self.send().status_code, 200)
        result = self.verify()
        self.assertEqual(result.status_code, 200)
        return result.json()["resetToken"]

    def complete(self, token, **changes):
        data = {"mobile": self.user.mobile, "resetToken": token,
                "password": "ReplacementPass739!", "confirmPassword": "ReplacementPass739!"}
        data.update(changes)
        return self.post("complete", data)

    def allow_resend(self):
        PasswordResetChallenge.objects.filter(mobile=self.user.mobile).update(
            last_sent_at=timezone.now() - timedelta(seconds=61))

    def test_page_login_link_and_legacy_redirect(self):
        self.assertContains(self.client.get("/login"), 'href="/forgot-password"')
        response = self.client.get("/forgot-password")
        self.assertContains(response, 'id="password-reset-form"')
        self.assertContains(response, 'name="confirmPassword"')
        self.assertContains(response, 'content="noindex, nofollow"')
        self.assertEqual(response["Cache-Control"], "no-store")
        self.assertIn("csrftoken", response.cookies)
        self.assertRedirects(self.client.get("/forgot-password.html"), "/forgot-password", status_code=301)

    def test_full_flow_consumes_grant_logs_out_sessions_and_allows_new_login(self):
        existing_session = Client()
        existing_session.force_login(self.user)
        self.client.force_login(self.user)
        token = self.grant()
        challenge = PasswordResetChallenge.objects.get(mobile=self.user.mobile)
        self.assertEqual(challenge.code_digest, "")
        self.assertNotEqual(challenge.token_digest, token)
        self.assertNotEqual(challenge.password_digest, self.user.password)
        self.assertEqual(self.verify().status_code, 400)
        response = self.complete(token)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["redirect"], "/login?reset=success")
        self.user.refresh_from_db()
        self.assertTrue(self.user.check_password("ReplacementPass739!"))
        self.assertFalse(self.user.check_password("OriginalPass482!"))
        self.assertEqual(self.user.status, User.Status.ACTIVE)
        self.assertEqual(self.client.get("/api/me").status_code, 401)
        self.assertEqual(existing_session.get("/api/me").status_code, 401)
        self.assertEqual(self.complete(token).status_code, 403)
        challenge.refresh_from_db()
        self.assertEqual(challenge.token_digest, "")
        self.assertEqual(challenge.send_count, 1)
        self.assertEqual(self.client.post("/api/login", json.dumps({"mobile": self.user.mobile,
                         "password": "OriginalPass482!"}), content_type="application/json").status_code, 401)
        self.assertEqual(self.client.post("/api/login", json.dumps({"mobile": self.user.mobile,
                         "password": "ReplacementPass739!"}), content_type="application/json").status_code, 200)

    def test_send_normalizes_persian_digits_and_hashes_code(self):
        response = self.send("۰۹۱۲۱۱۱۲۲۳۳")
        self.assertEqual(response.status_code, 200)
        self.sender.assert_called_once_with(self.user.mobile, "12345")
        challenge = PasswordResetChallenge.objects.get(mobile=self.user.mobile)
        self.assertEqual(challenge.code_digest, reset_digest(self.user.mobile, "code", "12345"))
        self.assertNotEqual(challenge.code_digest, signup_otp_digest(self.user.mobile, "12345"))
        self.assertNotIn("resetToken", response.json())
        self.assertEqual(self.verify("۱۲۳۴۵").status_code, 200)

    @override_settings(SMS_IR_API_KEY="test-private-key", SMS_IR_TEMPLATE_ID=511188)
    @patch("members.views.urlopen")
    def test_send_uses_existing_sms_ir_provider(self, urlopen):
        from .views import _send_otp_sms
        self.sender.side_effect = _send_otp_sms
        response = MagicMock()
        response.read.return_value = b'{"status": 1, "data": {"messageId": 123}}'
        urlopen.return_value.__enter__.return_value = response
        self.assertEqual(self.send().status_code, 200)
        request = urlopen.call_args.args[0]
        self.assertEqual(request.full_url, "https://api.sms.ir/v1/send/verify")
        self.assertEqual(request.get_header("X-api-key"), "test-private-key")
        self.assertEqual(json.loads(request.data), {"mobile": self.user.mobile, "templateId": 511188,
                         "parameters": [{"name": "Code", "value": "12345"}]})

    def test_unknown_and_inactive_numbers_have_same_response_without_sms(self):
        known = self.send().json()
        unknown = self.send("09120000000")
        self.assertEqual(unknown.status_code, 200)
        self.assertEqual(known, unknown.json())
        self.assertEqual(self.sender.call_count, 1)
        known_wrong = self.verify("99999")
        unknown_wrong = self.verify("99999", mobile="09120000000")
        self.assertEqual(known_wrong.status_code, unknown_wrong.status_code)
        self.assertEqual(known_wrong.json(), unknown_wrong.json())
        self.assertEqual(self.verify(mobile="09120000000").status_code, 400)
        self.user.is_active = False
        self.user.save(update_fields=["is_active"])
        self.allow_resend()
        self.assertEqual(self.send().json(), known)
        self.assertEqual(self.sender.call_count, 1)
        self.assertEqual(self.verify().status_code, 400)

    def test_unusable_password_cannot_be_reset(self):
        self.user.set_unusable_password()
        self.user.save(update_fields=["password"])
        self.assertEqual(self.send().status_code, 200)
        self.sender.assert_not_called()
        self.assertEqual(self.verify().status_code, 400)

    def test_provider_failure_invalidates_code(self):
        self.sender.side_effect = RuntimeError("offline")
        self.assertEqual(self.send().status_code, 502)
        self.assertEqual(PasswordResetChallenge.objects.get(mobile=self.user.mobile).code_digest, "")
        self.assertEqual(self.verify().status_code, 400)

    def test_resend_cooldown_and_hourly_limit_survive_password_reset(self):
        token = self.grant()
        self.assertEqual(self.complete(token).status_code, 200)
        blocked = self.send()
        self.assertEqual(blocked.status_code, 429)
        self.assertGreater(int(blocked["Retry-After"]), 0)
        for _ in range(4):
            self.allow_resend()
            self.assertEqual(self.send().status_code, 200)
        self.allow_resend()
        self.assertEqual(self.send().status_code, 429)
        self.assertEqual(self.sender.call_count, 5)
        PasswordResetChallenge.objects.filter(mobile=self.user.mobile).update(
            window_started_at=timezone.now() - timedelta(hours=2))
        self.assertEqual(self.send().status_code, 200)

    @override_settings(PASSWORD_RESET_MAX_IP_SENDS_PER_HOUR=2)
    def test_ip_limit_applies_across_numbers(self):
        self.assertEqual(self.send("09120000000").status_code, 200)
        self.assertEqual(self.send("09120000001").status_code, 200)
        self.assertEqual(self.send("09120000002").status_code, 429)

    def test_wrong_code_locks_challenge_after_five_attempts(self):
        self.send()
        for _ in range(5):
            self.assertEqual(self.verify("99999").status_code, 400)
        self.assertEqual(self.verify().status_code, 429)
        self.assertEqual(PasswordResetChallenge.objects.get(mobile=self.user.mobile).code_digest, "")

    def test_expired_code_cannot_verify(self):
        self.send()
        PasswordResetChallenge.objects.filter(mobile=self.user.mobile).update(expires_at=timezone.now())
        self.assertEqual(self.verify().status_code, 400)

    def test_signup_code_cannot_authorize_password_reset(self):
        now = timezone.now()
        SignupOTP.objects.create(mobile=self.user.mobile, code_digest=signup_otp_digest(self.user.mobile, "12345"),
                                 expires_at=now + timedelta(minutes=3), last_sent_at=now, window_started_at=now)
        self.assertEqual(self.verify().status_code, 400)
        self.assertEqual(self.complete("x" * 43).status_code, 403)

    def test_cannot_change_password_before_verification_or_for_other_phone(self):
        self.send()
        self.assertEqual(self.complete("x" * 43).status_code, 403)
        token = self.verify().json()["resetToken"]
        self.assertEqual(self.complete(token, mobile="09120000000").status_code, 403)
        self.assertEqual(self.complete("x" * 43).status_code, 403)
        self.user.refresh_from_db()
        self.assertTrue(self.user.check_password("OriginalPass482!"))

    def test_mismatch_and_weak_password_keep_grant_for_correction(self):
        token = self.grant()
        response = self.complete(token, confirmPassword="DifferentPass482!")
        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.json()["field"], "confirmPassword")
        response = self.complete(token, password="weak", confirmPassword="weak")
        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.json()["field"], "password")
        self.assertEqual(self.complete(token, confirmPassword=None).status_code, 400)
        self.assertEqual(self.complete(token, password="A1" * 65, confirmPassword="A1" * 65).status_code, 400)
        self.assertEqual(self.complete(token).status_code, 200)

    def test_expired_grant_resend_and_external_password_change_invalidate_token(self):
        token = self.grant()
        PasswordResetChallenge.objects.filter(mobile=self.user.mobile).update(expires_at=timezone.now())
        self.assertEqual(self.complete(token).status_code, 403)
        self.allow_resend()
        self.send()
        token = self.verify().json()["resetToken"]
        self.allow_resend()
        self.send()
        self.assertEqual(self.complete(token).status_code, 403)
        new_token = self.verify().json()["resetToken"]
        self.user.set_password("ChangedElsewhere482!")
        self.user.save(update_fields=["password"])
        self.assertEqual(self.complete(new_token).status_code, 403)

    def test_resend_invalidates_previous_code(self):
        self.send()
        self.allow_resend()
        with patch("members.password_reset.secrets.randbelow", return_value=9876):
            self.send()
        self.assertEqual(self.verify("12345").status_code, 400)
        self.assertEqual(self.verify("19876").status_code, 200)

    def test_reset_does_not_activate_pending_or_suspended_accounts(self):
        for status in (User.Status.PENDING, User.Status.SUSPENDED):
            self.user.status = status
            self.user.save(update_fields=["status"])
            token = self.grant()
            self.assertEqual(self.complete(token).status_code, 200)
            self.user.refresh_from_db()
            self.assertEqual(self.user.status, status)
            self.allow_resend()

    def test_endpoints_require_post_csrf_and_valid_json(self):
        strict = Client(enforce_csrf_checks=True)
        for action in ("send", "verify", "complete"):
            self.assertEqual(self.client.get(f"/api/password-reset/{action}").status_code, 405)
            self.assertEqual(self.post(action, {"mobile": self.user.mobile}, strict).status_code, 403)
            for value in ([], "invalid", None, {"mobile": "123"}):
                self.assertEqual(self.post(action, value).status_code, 400)
        strict.get("/forgot-password")
        response = strict.post("/api/password-reset/send", json.dumps({"mobile": self.user.mobile}),
                               content_type="application/json", HTTP_X_CSRFTOKEN=strict.cookies["csrftoken"].value)
        self.assertEqual(response.status_code, 200)
        self.assertIn("no-store", response["Cache-Control"])
