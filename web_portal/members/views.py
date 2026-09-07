import hashlib
import hmac
import json
import re
import secrets
from datetime import timedelta
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from django.conf import settings
from django.contrib.auth import authenticate, login, logout
from django.contrib.auth.password_validation import validate_password
from django.core.cache import cache
from django.core.exceptions import ValidationError
from django.db import IntegrityError, transaction
from django.http import FileResponse, Http404, JsonResponse
from django.shortcuts import render, redirect
from django.utils import timezone
from django.views.decorators.csrf import csrf_exempt, ensure_csrf_cookie
from django.views.decorators.http import require_GET, require_http_methods, require_POST

from .models import CoachProfile, LegacyMember, MembershipApplication, Plan, SignupOTP, User, WorkoutProgram, LoginEvent, OwnerAudit


PUBLIC_ROOT = settings.BASE_DIR.parent / "lifebox-landing"
PUBLIC_PAGES = {"index.html", "coaches.html", "login.html", "signup.html", "pending.html", "dashboard.html", "admin.html", "coach-panel.html"}
DIGITS = str.maketrans("۰۱۲۳۴۵۶۷۸۹٠١٢٣٤٥٦٧٨٩", "01234567890123456789")
MOBILE_RE = re.compile(r"^09\d{9}$")
NATIONAL_ID_RE = re.compile(r"^\d{10}$")
WEEKDAYS = {
    "saturday": "شنبه",
    "sunday": "یکشنبه",
    "monday": "دوشنبه",
    "tuesday": "سه‌شنبه",
    "wednesday": "چهارشنبه",
    "thursday": "پنج‌شنبه",
    "friday": "جمعه",
}


def normalize_digits(value):
    return re.sub(r"\s+", "", str(value or "").translate(DIGITS))


def signup_otp_digest(mobile, code):
    message = f"{mobile}:{code}".encode("utf-8")
    return hmac.new(settings.SECRET_KEY.encode("utf-8"), message, hashlib.sha256).hexdigest()


def _client_ip(request):
    return request.META.get("REMOTE_ADDR", "unknown")


def _ip_otp_limit_reached(request):
    cache_key = f"signup-otp-ip:{_client_ip(request)}"
    if cache.add(cache_key, 1, timeout=60 * 60):
        return False
    try:
        return cache.incr(cache_key) > settings.SIGNUP_OTP_MAX_IP_SENDS_PER_HOUR
    except ValueError:
        cache.set(cache_key, 1, timeout=60 * 60)
        return False


def _send_signup_otp(mobile, code):
    if not settings.SMS_IR_API_KEY:
        raise RuntimeError("SMS_IR_API_KEY is not configured")
    body = json.dumps(
        {
            "mobile": mobile,
            "templateId": settings.SMS_IR_TEMPLATE_ID,
            "parameters": [{"name": "Code", "value": code}],
        }
    ).encode("utf-8")
    request = Request(
        settings.SMS_IR_API_URL,
        data=body,
        headers={
            "X-API-KEY": settings.SMS_IR_API_KEY,
            "Content-Type": "application/json",
            "Accept": "application/json",
        },
        method="POST",
    )
    try:
        with urlopen(request, timeout=settings.SMS_IR_TIMEOUT_SECONDS) as response:
            result = json.loads(response.read().decode("utf-8"))
    except HTTPError as exc:
        try:
            result = json.loads(exc.read().decode("utf-8"))
            provider_message = result.get("message", "")
        except (UnicodeDecodeError, json.JSONDecodeError, AttributeError):
            provider_message = ""
        raise RuntimeError(provider_message or f"SMS.ir HTTP {exc.code}") from exc
    except (URLError, TimeoutError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise RuntimeError("SMS.ir is unavailable") from exc
    if not isinstance(result, dict) or result.get("status") != 1 or not isinstance(result.get("data"), dict):
        message = result.get("message", "SMS.ir rejected the request") if isinstance(result, dict) else "Invalid SMS.ir response"
        raise RuntimeError(str(message))
    return result["data"]


def body_json(request):
    try:
        value = json.loads(request.body.decode("utf-8"))
        return value if isinstance(value, dict) else None
    except (UnicodeDecodeError, json.JSONDecodeError):
        return None


def error(message, status=400, field=None):
    payload = {"ok": False, "message": message}
    if field:
        payload["field"] = field
    return JsonResponse(payload, status=status)


def split_name(full_name):
    parts = re.sub(r"\s+", " ", str(full_name or "")).strip().split(" ")
    return (parts[0], " ".join(parts[1:])) if len(parts) > 1 else (parts[0] if parts else "", "")


def find_legacy_member(mobile):
    normalized = normalize_digits(mobile)
    for member in LegacyMember.objects.only("id", "mobile", "plan", "used_sessions", "signup_time"):
        if normalize_digits(member.mobile) == normalized:
            return member
    return None


def public_user(user):
    application = getattr(user, "membership_application", None)
    legacy = None
    if application and application.legacy_member_id:
        legacy = LegacyMember.objects.filter(pk=application.legacy_member_id).first()
    plan_name = legacy.plan if legacy else application.plan.name if application else "—"
    joined_at = legacy.signup_time if legacy else application.requested_at.isoformat() if application else user.date_joined.isoformat()
    data = {
        "id": user.id,
        "fullName": user.get_full_name().strip() or user.mobile,
        "mobile": user.mobile,
        "nationalId": user.national_id,
        "address": user.address,
        "role": user.role,
        "status": user.status,
        "plan": plan_name,
        "sessionsUsed": legacy.used_sessions if legacy else 0,
        "joinedAt": joined_at,
        "lastLoginAt": user.last_login.isoformat() if user.last_login else None,
        "applicationId": application.id if application else None,
        "fittrackMemberId": application.legacy_member_id if application else None,
        "webLinked": True,
    }
    if user.role == User.Role.COACH:
        profile = getattr(user, "coach_profile", None)
        data["specialty"] = profile.specialty if profile else ""
        data["profileComplete"] = bool(user.get_full_name().strip() and profile and profile.specialty)
    return data


def reconcile_pending_user(user):
    application = getattr(user, "membership_application", None)
    if not application or application.status != MembershipApplication.Status.PENDING:
        return
    legacy = find_legacy_member(user.mobile)
    if legacy and legacy.embedding and legacy.face_image:
        with transaction.atomic():
            application.activate(legacy_member_id=legacy.id, paid_amount=legacy.payment or 0)


@ensure_csrf_cookie
def page(request, name):
    if name == 'admin.html' and not _is_admin(request.user):
        return redirect('/login.html')
    if name not in PUBLIC_PAGES or not (PUBLIC_ROOT / name).is_file():
        raise Http404
    response = render(request, name)
    response["Cache-Control"] = "no-store"
    return response


def _safe_public_path(relative):
    candidate = (PUBLIC_ROOT / relative).resolve()
    try:
        candidate.relative_to(PUBLIC_ROOT.resolve())
    except ValueError as exc:
        raise Http404 from exc
    if not candidate.is_file():
        raise Http404
    return candidate


@require_GET
def public_file(request, name):
    response = FileResponse(_safe_public_path(name).open("rb"))
    response["Cache-Control"] = "no-cache"
    return response


@require_GET
def asset_file(request, name):
    response = FileResponse(_safe_public_path(Path("assets") / name).open("rb"))
    response["Cache-Control"] = "public, max-age=86400"
    return response


@require_GET
def health(request):
    return JsonResponse({"ok": True, "service": "LifeBox Django", "fittrack": LegacyMember.objects.count()})


@require_GET
def plans_api(request):
    plans = Plan.objects.filter(is_active=True).values("id", "name", "gender", "price", "sessions_per_month")
    return JsonResponse({"ok": True, "plans": list(plans)})


@require_POST
def signup_otp_send_api(request):
    payload = body_json(request)
    if payload is None:
        return error("اطلاعات ارسال‌شده معتبر نیست.")
    mobile = normalize_digits(payload.get("mobile"))
    if not MOBILE_RE.fullmatch(mobile):
        return error("شماره موبایل باید ۱۱ رقم و با ۰۹ شروع شود.", field="mobile")
    if User.objects.filter(mobile=mobile).exists():
        return error("با این شماره موبایل قبلاً حساب ساخته شده است.", status=409, field="mobile")
    if _ip_otp_limit_reached(request):
        return error("تعداد درخواست‌های ارسال کد بیش از حد مجاز است؛ یک ساعت دیگر دوباره تلاش کنید.", status=429)

    now = timezone.now()
    challenge = SignupOTP.objects.filter(mobile=mobile).first()
    if challenge:
        resend_at = challenge.last_sent_at + timedelta(seconds=settings.SIGNUP_OTP_RESEND_SECONDS)
        if resend_at > now:
            retry_after = max(1, int((resend_at - now).total_seconds()) + 1)
            response = error(f"برای ارسال دوباره کد {retry_after} ثانیه صبر کنید.", status=429, field="otpCode")
            response["Retry-After"] = str(retry_after)
            return response
        if challenge.window_started_at + timedelta(hours=1) <= now:
            challenge.send_count = 0
            challenge.window_started_at = now
        if challenge.send_count >= settings.SIGNUP_OTP_MAX_SENDS_PER_HOUR:
            return error("حداکثر تعداد ارسال کد برای این شماره انجام شده است؛ یک ساعت دیگر دوباره تلاش کنید.", status=429, field="otpCode")

    code = str(10_000 + secrets.randbelow(90_000))
    digest = signup_otp_digest(mobile, code)
    expires_at = now + timedelta(seconds=settings.SIGNUP_OTP_TTL_SECONDS)
    if challenge:
        challenge.code_digest = digest
        challenge.expires_at = expires_at
        challenge.last_sent_at = now
        challenge.send_count += 1
        challenge.failed_attempts = 0
        challenge.save()
    else:
        challenge = SignupOTP.objects.create(
            mobile=mobile,
            code_digest=digest,
            expires_at=expires_at,
            last_sent_at=now,
            window_started_at=now,
        )
    try:
        _send_signup_otp(mobile, code)
    except RuntimeError:
        SignupOTP.objects.filter(pk=challenge.pk, code_digest=digest).update(code_digest="", expires_at=now)
        return error("ارسال پیامک انجام نشد؛ کمی بعد دوباره تلاش کنید.", status=502, field="otpCode")
    return JsonResponse(
        {
            "ok": True,
            "message": "کد تأیید برای شما پیامک شد.",
            "expiresIn": settings.SIGNUP_OTP_TTL_SECONDS,
            "resendAfter": settings.SIGNUP_OTP_RESEND_SECONDS,
        }
    )


@require_POST
def signup_api(request):
    payload = body_json(request)
    if payload is None:
        return error("اطلاعات ارسال‌شده معتبر نیست.")
    full_name = re.sub(r"\s+", " ", str(payload.get("fullName", ""))).strip()[:150]
    mobile = normalize_digits(payload.get("mobile"))
    national_id = normalize_digits(payload.get("nationalId"))
    address = re.sub(r"\s+", " ", str(payload.get("address", ""))).strip()[:500]
    password = str(payload.get("password", ""))
    otp_code = normalize_digits(payload.get("otpCode"))
    plan_id = payload.get("planId")
    if len(full_name) < 3:
        return error("نام و نام خانوادگی را کامل وارد کنید.", field="fullName")
    if not MOBILE_RE.fullmatch(mobile):
        return error("شماره موبایل باید ۱۱ رقم و با ۰۹ شروع شود.", field="mobile")
    if not re.fullmatch(r"\d{5}", otp_code):
        return error("کد تأیید پنج‌رقمی را وارد کنید.", field="otpCode")
    if not NATIONAL_ID_RE.fullmatch(national_id):
        return error("کد ملی باید دقیقاً ۱۰ رقم باشد.", field="nationalId")
    if len(address) < 8:
        return error("آدرس کامل محل سکونت را وارد کنید.", field="address")
    try:
        plan = Plan.objects.get(pk=plan_id, is_active=True)
    except (Plan.DoesNotExist, ValueError, TypeError):
        return error("یکی از پلن‌های فعال را انتخاب کنید.", field="planId")
    try:
        validate_password(password)
    except ValidationError as exc:
        return error(" ".join(exc.messages), field="password")
    first_name, last_name = split_name(full_name)
    legacy = find_legacy_member(mobile)
    try:
        with transaction.atomic():
            challenge = SignupOTP.objects.select_for_update().filter(mobile=mobile).first()
            now = timezone.now()
            if not challenge or not challenge.code_digest or challenge.expires_at <= now:
                return error("کد تأیید منقضی شده است؛ کد جدیدی دریافت کنید.", field="otpCode")
            if challenge.failed_attempts >= settings.SIGNUP_OTP_MAX_ATTEMPTS:
                return error("تعداد تلاش‌های ناموفق بیش از حد مجاز است؛ کد جدیدی دریافت کنید.", status=429, field="otpCode")
            expected = signup_otp_digest(mobile, otp_code)
            if not hmac.compare_digest(challenge.code_digest, expected):
                challenge.failed_attempts += 1
                if challenge.failed_attempts >= settings.SIGNUP_OTP_MAX_ATTEMPTS:
                    challenge.code_digest = ""
                challenge.save(update_fields=["failed_attempts", "code_digest", "updated_at"])
                return error("کد تأیید درست نیست.", field="otpCode")
            user = User.objects.create_user(
                mobile=mobile,
                password=password,
                first_name=first_name,
                last_name=last_name,
                national_id=national_id,
                address=address,
                status=User.Status.ACTIVE if legacy else User.Status.PENDING,
            )
            application = MembershipApplication.objects.create(
                user=user,
                plan=plan,
                status=MembershipApplication.Status.ACTIVE if legacy else MembershipApplication.Status.PENDING,
                legacy_member_id=legacy.id if legacy else None,
                face_registered=bool(legacy),
                activated_at=timezone.now() if legacy else None,
            )
            challenge.delete()
    except IntegrityError:
        return error("با این شماره موبایل یا کد ملی قبلاً حساب ساخته شده است.", status=409, field="mobile")
    login(request, user)
    return JsonResponse({"ok": True, "user": public_user(user), "applicationId": application.id}, status=201)


@require_POST
def login_api(request):
    payload = body_json(request) or {}
    mobile = normalize_digits(payload.get("mobile"))
    limit_key = "login-attempt:" + hashlib.sha256((mobile + _client_ip(request)).encode()).hexdigest()
    if cache.get(limit_key, 0) >= 10:
        return error("تلاش‌های ورود بیش از حد است؛ ۱۵ دقیقه بعد دوباره تلاش کنید.", status=429)
    user = authenticate(request, mobile=mobile, password=str(payload.get("password", "")))
    if not user:
        cache.set(limit_key, cache.get(limit_key, 0) + 1, 900)
        return error("شماره موبایل یا رمز عبور درست نیست.", status=401)
    if user.status == User.Status.SUSPENDED:
        return error("این حساب تعلیق شده است؛ با مدیریت تماس بگیرید.", status=403)
    login(request, user)
    cache.delete(limit_key)
    LoginEvent.objects.create(user=user)
    return JsonResponse({"ok": True, "user": public_user(user)})


@require_POST
def logout_api(request):
    logout(request)
    return JsonResponse({"ok": True})


@require_GET
def me_api(request):
    if not request.user.is_authenticated:
        return error("برای ادامه وارد حساب شوید.", status=401)
    if request.user.status == User.Status.SUSPENDED:
        logout(request)
        return error('این حساب تعلیق شده است.', status=403)
    reconcile_pending_user(request.user)
    request.user.refresh_from_db()
    return JsonResponse({"ok": True, "user": public_user(request.user)})


def _is_admin(user):
    return user.is_authenticated and user.is_active and user.status == User.Status.ACTIVE and (user.is_superuser or user.role == User.Role.ADMIN)


def _is_coach(user):
    return user.is_authenticated and user.role == User.Role.COACH and user.status == User.Status.ACTIVE


def public_coach(user):
    profile, _ = CoachProfile.objects.get_or_create(user=user)
    plans = list(profile.allowed_plans.filter(is_active=True).order_by("price", "name"))
    return {
        "id": user.id,
        "mobile": user.mobile,
        "fullName": user.get_full_name().strip(),
        "specialty": profile.specialty,
        "bio": profile.bio,
        "planIds": [plan.id for plan in plans],
        "plans": [plan.name for plan in plans],
        "profileComplete": bool(user.get_full_name().strip() and profile.specialty),
    }


@require_GET
def admin_users_api(request):
    if not _is_admin(request.user):
        return error("دسترسی مجاز نیست.", status=403)
    search = request.GET.get("search", "").strip()[:80]
    users = User.objects.select_related("membership_application__plan").order_by("-date_joined")
    if search:
        normalized = normalize_digits(search)
        users = [user for user in users if search.casefold() in user.get_full_name().casefold() or normalized in user.mobile]
    return JsonResponse({"ok": True, "users": [public_user(user) for user in users], "source": "django"})


@require_http_methods(["PATCH"])
def admin_user_status_api(request, user_id):
    if not _is_admin(request.user):
        return error("دسترسی مجاز نیست.", status=403)
    payload = body_json(request) or {}
    status = payload.get("status")
    if status not in {User.Status.ACTIVE, User.Status.SUSPENDED}:
        return error("وضعیت انتخاب‌شده معتبر نیست.")
    user = User.objects.filter(pk=user_id).first()
    if not user:
        return error("کاربر پیدا نشد.", status=404)
    if user.pk == request.user.pk or user.role == User.Role.ADMIN:
        return error("نمی‌توانید حساب خودتان را تعلیق کنید.")
    user.status = status
    user.save(update_fields=["status"])
    OwnerAudit.objects.create(actor=request.user, action=f'تغییر وضعیت حساب {user.pk}: {status}')
    return JsonResponse({"ok": True, "status": status})


@require_http_methods(["GET", "PATCH"])
def coach_profile_api(request):
    if not _is_coach(request.user):
        return error("دسترسی مربی لازم است.", status=403)
    if request.method == "GET":
        return JsonResponse({"ok": True, "coach": public_coach(request.user)})
    payload = body_json(request) or {}
    full_name = re.sub(r"\s+", " ", str(payload.get("fullName", ""))).strip()[:150]
    specialty = re.sub(r"\s+", " ", str(payload.get("specialty", ""))).strip()[:160]
    bio = str(payload.get("bio", "")).strip()[:1500]
    if len(full_name) < 3:
        return error("نام و نام خانوادگی را کامل وارد کنید.", field="fullName")
    if len(specialty) < 2:
        return error("تخصص مربی را وارد کنید.", field="specialty")
    first_name, last_name = split_name(full_name)
    with transaction.atomic():
        request.user.first_name = first_name
        request.user.last_name = last_name
        request.user.save(update_fields=["first_name", "last_name"])
        profile, _ = CoachProfile.objects.get_or_create(user=request.user)
        profile.specialty = specialty
        profile.bio = bio
        profile.save(update_fields=["specialty", "bio", "updated_at"])
    return JsonResponse({"ok": True, "coach": public_coach(request.user)})


def _coach_member_queryset(coach):
    profile, _ = CoachProfile.objects.get_or_create(user=coach)
    allowed = profile.allowed_plans.filter(is_active=True)
    return User.objects.filter(
        role=User.Role.MEMBER,
        status=User.Status.ACTIVE,
        membership_application__status=MembershipApplication.Status.ACTIVE,
        membership_application__plan__in=allowed,
    ).select_related("membership_application__plan").distinct().order_by(
        "first_name", "last_name", "mobile"
    )


@require_GET
def coach_members_api(request):
    if not _is_coach(request.user):
        return error("دسترسی مربی لازم است.", status=403)
    search = request.GET.get("search", "").strip()[:80]
    members = _coach_member_queryset(request.user)
    if search:
        normalized = normalize_digits(search)
        members = [
            member for member in members
            if search.casefold() in member.get_full_name().casefold() or normalized in member.mobile
        ]
    data = [
        {
            "id": member.id,
            "fullName": member.get_full_name().strip() or member.mobile,
            "mobile": member.mobile,
            "plan": member.membership_application.plan.name,
        }
        for member in members[:200]
    ]
    return JsonResponse({"ok": True, "members": data})


def _legacy_schedule(exercises):
    movements = [line.strip() for line in str(exercises or "").splitlines() if line.strip()]
    return [{"weekday": "unspecified", "label": "بدون روز مشخص", "movements": movements}] if movements else []


def _program_payload(program):
    days = program.schedule_json if isinstance(program.schedule_json, list) and program.schedule_json else _legacy_schedule(program.exercises)
    return {
        "id": program.id,
        "title": program.title,
        "exercises": program.exercises,
        "durationWeeks": program.duration_weeks,
        "days": days,
        "updatedAt": program.updated_at.isoformat(),
    }


def _validate_weekly_schedule(payload):
    try:
        duration_weeks = int(payload.get("durationWeeks", 4))
    except (TypeError, ValueError):
        return None, None, error("مدت برنامه باید یک عدد باشد.", field="durationWeeks")
    if not 1 <= duration_weeks <= 12:
        return None, None, error("مدت برنامه باید بین ۱ تا ۱۲ هفته باشد.", field="durationWeeks")

    days = payload.get("days")
    if not isinstance(days, list) or not 2 <= len(days) <= 7:
        return None, None, error("تعداد روزهای تمرین باید بین ۲ تا ۷ روز باشد.", field="trainingDays")
    normalized_days = []
    used_weekdays = set()
    flattened = []
    for index, day in enumerate(days):
        if not isinstance(day, dict):
            return None, None, error("اطلاعات یکی از روزهای تمرین معتبر نیست.", field="trainingDays")
        weekday = str(day.get("weekday", "")).strip().lower()
        if weekday not in WEEKDAYS:
            return None, None, error(f"روز تمرین شماره {index + 1} را انتخاب کنید.", field="trainingDays")
        if weekday in used_weekdays:
            return None, None, error("هر روز هفته را فقط یک بار انتخاب کنید.", field="trainingDays")
        used_weekdays.add(weekday)
        movements = day.get("movements")
        if not isinstance(movements, list):
            return None, None, error(f"حرکت‌های {WEEKDAYS[weekday]} معتبر نیست.", field="trainingDays")
        cleaned_movements = [re.sub(r"\s+", " ", str(item)).strip()[:300] for item in movements]
        cleaned_movements = [item for item in cleaned_movements if item]
        if not cleaned_movements:
            return None, None, error(f"برای {WEEKDAYS[weekday]} حداقل یک حرکت وارد کنید.", field="trainingDays")
        if len(cleaned_movements) > 20:
            return None, None, error(f"برای {WEEKDAYS[weekday]} حداکثر ۲۰ حرکت مجاز است.", field="trainingDays")
        normalized_days.append({
            "weekday": weekday,
            "label": WEEKDAYS[weekday],
            "movements": cleaned_movements,
        })
        flattened.append(f"{WEEKDAYS[weekday]}:")
        flattened.extend(cleaned_movements)
    return duration_weeks, normalized_days, "\n".join(flattened)


@require_http_methods(["GET", "POST"])
def coach_programs_api(request):
    if not _is_coach(request.user):
        return error("دسترسی مربی لازم است.", status=403)
    if request.method == "POST":
        payload = body_json(request) or {}
        try:
            member_id = int(payload.get("memberId"))
        except (TypeError, ValueError):
            return error("ورزشکار انتخاب‌شده معتبر نیست.", field="memberId")
        title = re.sub(r"\s+", " ", str(payload.get("title", ""))).strip()[:180]
        if not title:
            return error("عنوان برنامه را وارد کنید.", field="title")
        duration_weeks, days, flattened_or_error = _validate_weekly_schedule(payload)
        if isinstance(flattened_or_error, JsonResponse):
            return flattened_or_error
        member = _coach_member_queryset(request.user).filter(pk=member_id).first()
        if not member:
            return error("این ورزشکار در پلن‌های مجاز شما نیست.", status=403)
        program, _ = WorkoutProgram.objects.update_or_create(
            coach=request.user,
            member=member,
            defaults={
                "title": title,
                "exercises": flattened_or_error[:8000],
                "duration_weeks": duration_weeks,
                "schedule_json": days,
            },
        )
        return JsonResponse({"ok": True, "programId": program.id})
    programs = WorkoutProgram.objects.filter(coach=request.user).select_related("member")
    data = []
    for program in programs:
        item = _program_payload(program)
        item.update({
            "memberId": program.member_id,
            "memberName": program.member.get_full_name().strip() or program.member.mobile,
        })
        data.append(item)
    return JsonResponse({"ok": True, "programs": data})


@require_http_methods(["DELETE"])
def coach_program_api(request, program_id):
    if not _is_coach(request.user):
        return error("دسترسی مربی لازم است.", status=403)
    program = WorkoutProgram.objects.filter(pk=program_id, coach=request.user).first()
    if not program:
        return error("برنامه تمرینی پیدا نشد.", status=404)
    program.delete()
    return JsonResponse({"ok": True})


@require_GET
def member_program_api(request):
    if not request.user.is_authenticated or request.user.role != User.Role.MEMBER:
        return error("دسترسی عضو لازم است.", status=403)
    program = WorkoutProgram.objects.filter(member=request.user).select_related("coach").first()
    if not program:
        return JsonResponse({"ok": True, "program": None})
    data = _program_payload(program)
    data["coachName"] = program.coach.get_full_name().strip() or program.coach.mobile
    return JsonResponse({"ok": True, "program": data})


def _desktop_authorized(request):
    provided = request.headers.get("Authorization", "")
    return provided == f"Bearer {settings.FITTRACK_DESKTOP_API_TOKEN}"


def _desktop_plan_payload(plan):
    return {
        "id": plan.id,
        "name": plan.name,
        "gender": plan.gender,
        "price": plan.price,
        "sessionsPerMonth": plan.sessions_per_month,
        "isActive": plan.is_active,
    }


def _desktop_plan_values(payload, current=None):
    name = re.sub(r"\s+", " ", str(payload.get("name", current.name if current else ""))).strip()[:160]
    gender = str(payload.get("gender", current.gender if current else Plan.Gender.ALL))
    try:
        price = int(payload.get("price", current.price if current else 0))
        sessions = int(payload.get("sessionsPerMonth", current.sessions_per_month if current else 0))
    except (TypeError, ValueError):
        return None, error("مبلغ و تعداد جلسات باید عدد معتبر باشند.")
    if len(name) < 3:
        return None, error("نام پلن باید حداقل سه کاراکتر باشد.", field="name")
    if gender not in Plan.Gender.values:
        return None, error("جنسیت پلن معتبر نیست.", field="gender")
    if price < 0:
        return None, error("مبلغ پلن نمی‌تواند منفی باشد.", field="price")
    if sessions < 1 or sessions > 60:
        return None, error("تعداد جلسات ماهانه باید بین ۱ تا ۶۰ باشد.", field="sessionsPerMonth")
    return {
        "name": name,
        "gender": gender,
        "price": price,
        "sessions_per_month": sessions,
        "is_active": bool(payload.get("isActive", current.is_active if current else True)),
    }, None


@csrf_exempt
@require_http_methods(["GET", "POST"])
def desktop_plans_api(request):
    if not _desktop_authorized(request):
        return error("توکن Life Box معتبر نیست.", status=401)
    if request.method == "GET":
        plans = Plan.objects.all().order_by("price", "name")
        return JsonResponse({"ok": True, "plans": [_desktop_plan_payload(plan) for plan in plans]})
    values, plan_error = _desktop_plan_values(body_json(request) or {})
    if plan_error:
        return plan_error
    try:
        plan = Plan.objects.create(**values)
    except IntegrityError:
        return error("پلنی با این نام قبلاً ساخته شده است.", status=409, field="name")
    return JsonResponse({"ok": True, "plan": _desktop_plan_payload(plan)}, status=201)


@csrf_exempt
@require_http_methods(["PATCH"])
def desktop_plan_api(request, plan_id):
    if not _desktop_authorized(request):
        return error("توکن Life Box معتبر نیست.", status=401)
    plan = Plan.objects.filter(pk=plan_id).first()
    if not plan:
        return error("پلن پیدا نشد.", status=404)
    values, plan_error = _desktop_plan_values(body_json(request) or {}, plan)
    if plan_error:
        return plan_error
    for key, value in values.items():
        setattr(plan, key, value)
    try:
        plan.save(update_fields=list(values))
    except IntegrityError:
        return error("پلنی با این نام قبلاً ساخته شده است.", status=409, field="name")
    return JsonResponse({"ok": True, "plan": _desktop_plan_payload(plan)})


def _desktop_plan_selection(payload):
    plan_ids = payload.get("planIds")
    if not isinstance(plan_ids, list) or not plan_ids:
        return None, error("حداقل یک پلن مجاز برای مربی انتخاب کنید.", field="planIds")
    try:
        normalized = {int(value) for value in plan_ids}
    except (TypeError, ValueError):
        return None, error("فهرست پلن‌های مربی معتبر نیست.", field="planIds")
    plans = list(Plan.objects.filter(pk__in=normalized, is_active=True))
    if len(plans) != len(normalized):
        return None, error("یکی از پلن‌های انتخاب‌شده فعال نیست.", field="planIds")
    return plans, None


@csrf_exempt
@require_http_methods(["GET", "POST"])
def desktop_coaches_api(request):
    if not _desktop_authorized(request):
        return error("توکن Life Box معتبر نیست.", status=401)
    if request.method == "GET":
        coaches = User.objects.filter(role=User.Role.COACH).select_related("coach_profile").order_by("mobile")
        return JsonResponse({"ok": True, "coaches": [public_coach(coach) for coach in coaches]})
    payload = body_json(request) or {}
    mobile = normalize_digits(payload.get("mobile"))
    password = str(payload.get("password", ""))
    if not MOBILE_RE.fullmatch(mobile):
        return error("شماره موبایل باید ۱۱ رقم و با ۰۹ شروع شود.", field="mobile")
    if User.objects.filter(mobile=mobile).exists():
        return error("با این شماره موبایل قبلاً حساب ساخته شده است.", status=409, field="mobile")
    try:
        validate_password(password)
    except ValidationError as exc:
        return error(" ".join(exc.messages), field="password")
    plans, plan_error = _desktop_plan_selection(payload)
    if plan_error:
        return plan_error
    with transaction.atomic():
        coach = User.objects.create_user(
            mobile=mobile,
            password=password,
            role=User.Role.COACH,
            status=User.Status.ACTIVE,
        )
        profile = CoachProfile.objects.create(user=coach)
        profile.allowed_plans.set(plans)
    return JsonResponse({"ok": True, "coach": public_coach(coach)}, status=201)


@csrf_exempt
@require_http_methods(["PATCH"])
def desktop_coach_api(request, coach_id):
    if not _desktop_authorized(request):
        return error("توکن Life Box معتبر نیست.", status=401)
    coach = User.objects.filter(pk=coach_id, role=User.Role.COACH).first()
    if not coach:
        return error("حساب مربی پیدا نشد.", status=404)
    payload = body_json(request) or {}
    plans, plan_error = _desktop_plan_selection(payload)
    if plan_error:
        return plan_error
    password = str(payload.get("password", ""))
    if password:
        try:
            validate_password(password, user=coach)
        except ValidationError as exc:
            return error(" ".join(exc.messages), field="password")
    with transaction.atomic():
        if password:
            coach.set_password(password)
            coach.save(update_fields=["password"])
        profile, _ = CoachProfile.objects.get_or_create(user=coach)
        profile.allowed_plans.set(plans)
    return JsonResponse({"ok": True, "coach": public_coach(coach)})


@csrf_exempt
@require_http_methods(["PATCH"])
def desktop_member_password_api(request, legacy_member_id):
    if not _desktop_authorized(request):
        return error("توکن Life Box معتبر نیست.", status=401)
    application = MembershipApplication.objects.select_related("user").filter(
        legacy_member_id=legacy_member_id,
        user__role=User.Role.MEMBER,
    ).first()
    if not application:
        return error(
            "این عضو هنوز حساب متصل در سایت ندارد؛ ابتدا باید با همین شماره موبایل در سایت ثبت‌نام کند.",
            status=404,
        )
    payload = body_json(request) or {}
    password = str(payload.get("password", ""))
    try:
        validate_password(password, user=application.user)
    except ValidationError as exc:
        return error(" ".join(exc.messages), field="password")
    application.user.set_password(password)
    application.user.save(update_fields=["password"])
    return JsonResponse({
        "ok": True,
        "mobile": application.user.mobile,
        "message": "رمز ورود سایت با موفقیت تغییر کرد.",
    })


@require_GET
def desktop_applications_api(request):
    if not _desktop_authorized(request):
        return error("توکن Life Box معتبر نیست.", status=401)
    mobile = normalize_digits(request.GET.get("mobile", ""))
    applications = MembershipApplication.objects.select_related("user", "plan").filter(status=MembershipApplication.Status.PENDING)
    if mobile:
        applications = applications.filter(user__mobile=mobile)
    data = [
        {
            "id": item.id,
            "fullName": item.user.get_full_name(),
            "firstName": item.user.first_name,
            "lastName": item.user.last_name,
            "mobile": item.user.mobile,
            "nationalId": item.user.national_id,
            "address": item.user.address,
            "plan": item.plan.name,
            "planId": item.plan_id,
            "gender": item.plan.gender,
            "price": item.plan.price,
            "requestedAt": item.requested_at.isoformat(),
            "status": item.status,
        }
        for item in applications[:200]
    ]
    return JsonResponse({"ok": True, "applications": data})


@csrf_exempt
@require_POST
def desktop_activate_api(request, application_id):
    if not _desktop_authorized(request):
        return error("توکن Life Box معتبر نیست.", status=401)
    payload = body_json(request) or {}
    try:
        legacy_member_id = int(payload.get("legacyMemberId"))
        paid_amount = max(0, int(payload.get("paidAmount", 0)))
    except (TypeError, ValueError):
        return error("شناسه عضو یا مبلغ پرداخت معتبر نیست.")
    application = MembershipApplication.objects.select_related("user").filter(pk=application_id).first()
    if not application:
        return error("درخواست عضویت پیدا نشد.", status=404)
    if application.status != MembershipApplication.Status.PENDING:
        return error("این درخواست قبلاً تعیین تکلیف شده است.", status=409)
    legacy = LegacyMember.objects.filter(pk=legacy_member_id).first()
    if not legacy or normalize_digits(legacy.mobile) != application.user.mobile:
        return error("عضو ثبت‌شده در Life Box با این درخواست مطابقت ندارد.", status=409)
    with transaction.atomic():
        application.activate(legacy_member_id=legacy_member_id, paid_amount=paid_amount)
    return JsonResponse({"ok": True, "user": public_user(application.user)})

# Create your views here.
