"""SMS password recovery. Signup codes and reset grants are separate credentials."""
import hashlib
import hmac
import re
import secrets
from datetime import timedelta

from django.conf import settings
from django.contrib.auth import logout
from django.contrib.auth.password_validation import validate_password
from django.core.cache import cache
from django.core.exceptions import ValidationError
from django.db import transaction
from django.http import JsonResponse
from django.utils import timezone
from django.views.decorators.cache import never_cache
from django.views.decorators.http import require_POST

from .models import PasswordResetChallenge, User
from .views import MOBILE_RE, _client_ip, _send_otp_sms, body_json, error, normalize_digits


def reset_digest(mobile, kind, value):
    message = f"password-reset:{mobile}:{kind}:{value}".encode()
    return hmac.new(settings.SECRET_KEY.encode(), message, hashlib.sha256).hexdigest()


def _input(request):
    payload = body_json(request)
    if payload is None:
        return None, None, error("اطلاعات ارسال‌شده معتبر نیست.")
    mobile = normalize_digits(payload.get("mobile"))
    if not MOBILE_RE.fullmatch(mobile):
        return None, None, error("شماره موبایل باید ۱۱ رقم و با ۰۹ شروع شود.", field="mobile")
    return payload, mobile, None


def _eligible(challenge):
    user = challenge.user
    return bool(user and user.mobile == challenge.mobile and user.is_active and user.has_usable_password()
                and hmac.compare_digest(challenge.password_digest,
                                        reset_digest(challenge.mobile, "password", user.password)))


@never_cache
@require_POST
def send(request):
    _, mobile, invalid = _input(request)
    if invalid is not None:
        return invalid
    key = f"password-reset-ip:{_client_ip(request)}"
    if cache.add(key, 1, timeout=3600):
        count = 1
    else:
        try:
            count = cache.incr(key)
        except ValueError:
            cache.set(key, 1, timeout=3600)
            count = 1
    if count > settings.PASSWORD_RESET_MAX_IP_SENDS_PER_HOUR:
        return error("تعداد درخواست‌ها بیش از حد مجاز است؛ یک ساعت دیگر تلاش کنید.", status=429)

    now = timezone.now()
    code = str(10_000 + secrets.randbelow(90_000))
    digest = reset_digest(mobile, "code", code)
    with transaction.atomic():
        challenge, _ = PasswordResetChallenge.objects.select_for_update().get_or_create(
            mobile=mobile,
            defaults={"expires_at": now, "last_sent_at": now - timedelta(hours=1), "window_started_at": now},
        )
        retry_at = challenge.last_sent_at + timedelta(seconds=settings.PASSWORD_RESET_RESEND_SECONDS)
        if retry_at > now:
            retry_after = max(1, int((retry_at - now).total_seconds()) + 1)
            response = error(f"برای ارسال دوباره کد {retry_after} ثانیه صبر کنید.", status=429)
            response["Retry-After"] = str(retry_after)
            return response
        if challenge.window_started_at + timedelta(hours=1) <= now:
            challenge.window_started_at = now
            challenge.send_count = 0
        if challenge.send_count >= settings.PASSWORD_RESET_MAX_SENDS_PER_HOUR:
            return error("حداکثر ارسال کد برای این شماره انجام شده است؛ یک ساعت دیگر تلاش کنید.", status=429)
        user = User.objects.filter(mobile=mobile, is_active=True).first()
        if user and not user.has_usable_password():
            user = None
        challenge.user = user
        challenge.password_digest = reset_digest(mobile, "password", user.password) if user else ""
        # Decoy challenges give unknown numbers the same failed-code behavior.
        challenge.code_digest = digest
        challenge.token_digest = ""
        challenge.expires_at = now + timedelta(seconds=settings.PASSWORD_RESET_OTP_TTL_SECONDS)
        challenge.last_sent_at = now
        challenge.send_count += 1
        challenge.failed_attempts = 0
        challenge.save()
    if user:
        try:
            _send_otp_sms(mobile, code)
        except RuntimeError:
            PasswordResetChallenge.objects.filter(pk=challenge.pk, code_digest=digest).update(
                code_digest="", expires_at=now,
            )
            return error("ارسال پیامک انجام نشد؛ کمی بعد دوباره تلاش کنید.", status=502)
    # An unknown/inactive number gets the same response, without an SMS or reset grant.
    return JsonResponse({"ok": True, "message": "اگر با این شماره حساب دارید، کد تأیید برای شما پیامک می‌شود.",
                         "expiresIn": settings.PASSWORD_RESET_OTP_TTL_SECONDS,
                         "resendAfter": settings.PASSWORD_RESET_RESEND_SECONDS})


@never_cache
@require_POST
def verify(request):
    payload, mobile, invalid = _input(request)
    if invalid is not None:
        return invalid
    code = normalize_digits(payload.get("otpCode"))
    if not re.fullmatch(r"[0-9]{5}", code):
        return error("کد تأیید پنج‌رقمی را وارد کنید.", field="otpCode")
    with transaction.atomic():
        challenge = PasswordResetChallenge.objects.select_for_update().filter(mobile=mobile).first()
        now = timezone.now()
        if challenge and challenge.failed_attempts >= settings.PASSWORD_RESET_MAX_ATTEMPTS:
            return error("تعداد تلاش‌های ناموفق بیش از حد مجاز است؛ کد جدیدی دریافت کنید.", status=429, field="otpCode")
        if not challenge or not challenge.code_digest or challenge.expires_at <= now:
            return error("کد تأیید معتبر نیست یا منقضی شده است؛ کد جدیدی دریافت کنید.", field="otpCode")
        if not hmac.compare_digest(challenge.code_digest, reset_digest(mobile, "code", code)):
            challenge.failed_attempts += 1
            if challenge.failed_attempts >= settings.PASSWORD_RESET_MAX_ATTEMPTS:
                challenge.code_digest = ""
            challenge.save(update_fields=["failed_attempts", "code_digest"])
            return error("کد تأیید معتبر نیست یا منقضی شده است؛ کد جدیدی دریافت کنید.", field="otpCode")
        if not _eligible(challenge):
            return error("کد تأیید معتبر نیست یا منقضی شده است؛ کد جدیدی دریافت کنید.", field="otpCode")
        token = secrets.token_urlsafe(32)
        challenge.code_digest = ""
        challenge.token_digest = reset_digest(mobile, "token", token)
        challenge.expires_at = now + timedelta(seconds=settings.PASSWORD_RESET_TOKEN_TTL_SECONDS)
        challenge.save(update_fields=["code_digest", "token_digest", "expires_at"])
    return JsonResponse({"ok": True, "resetToken": token, "expiresIn": settings.PASSWORD_RESET_TOKEN_TTL_SECONDS})


@never_cache
@require_POST
def complete(request):
    payload, mobile, invalid = _input(request)
    if invalid is not None:
        return invalid
    token = payload.get("resetToken")
    if not isinstance(token, str) or not 40 <= len(token) <= 100:
        return error("ابتدا کد پیامکی را تأیید کنید.", status=403)
    with transaction.atomic():
        challenge = PasswordResetChallenge.objects.select_for_update().filter(mobile=mobile).first()
        now = timezone.now()
        if (not challenge or not challenge.token_digest or challenge.expires_at <= now
                or not hmac.compare_digest(challenge.token_digest, reset_digest(mobile, "token", token))
                or not _eligible(challenge)):
            return error("مهلت تغییر رمز تمام شده است؛ دوباره کد تأیید دریافت کنید.", status=403)
        # Lock the account too, so two valid reset requests cannot overwrite each other.
        user = User.objects.select_for_update().get(pk=challenge.user_id)
        challenge.user = user
        if not _eligible(challenge):
            return error("رمز حساب تغییر کرده است؛ کد جدیدی دریافت کنید.", status=403)
        password = payload.get("password")
        confirmation = payload.get("confirmPassword")
        if not isinstance(password, str) or len(password) > 128:
            return error("رمز عبور باید حداکثر ۱۲۸ کاراکتر باشد.", field="password")
        if len(password) < 10 or not re.search(r"[A-Za-z]", password) or not re.search(r"[0-9]", password):
            return error("حداقل ۱۰ کاراکتر و ترکیبی از حرف و عدد انتخاب کنید.", field="password")
        if password != confirmation:
            return error("تکرار رمز عبور با رمز جدید یکسان نیست.", field="confirmPassword")
        try:
            validate_password(password, user=user)
        except ValidationError as exc:
            return error(" ".join(exc.messages), field="password")
        user.set_password(password)
        user.save(update_fields=["password"])
        # Keep the send counters after consumption to preserve the hourly limit.
        challenge.code_digest = challenge.token_digest = challenge.password_digest = ""
        challenge.expires_at = now
        challenge.save(update_fields=["code_digest", "token_digest", "password_digest", "expires_at"])
    logout(request)
    return JsonResponse({"ok": True, "message": "رمز عبور تغییر کرد. با رمز جدید وارد شوید.", "redirect": "/login?reset=success"})
