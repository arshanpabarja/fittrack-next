"""Personal member workspace. Every record is scoped to the authenticated member."""
import re
import sqlite3
from contextlib import closing
from datetime import timedelta
from functools import wraps

from django.conf import settings
from django.contrib.auth import update_session_auth_hash
from django.contrib.auth.password_validation import validate_password
from django.contrib.sessions.models import Session
from django.core.exceptions import ValidationError
from django.db import transaction
from django.http import HttpResponse, JsonResponse
from django.utils import timezone
from django.views.decorators.cache import never_cache
from django.views.decorators.http import require_http_methods

from app.domain.dates import gregorian_to_jalali, membership_expires_at, membership_expired
from app.domain.membership import session_allowance
from .coaching import attendance_for, number, payload, program_data, text
from .insights import calendar_date
from .models import (Exercise, GymSyncRecord, LegacyMember, MemberPreferences,
                     MemberRequest, MemberWorkout, TrainingSession, User, WorkoutProgram)
from .views import error

REQUEST_KINDS = {
    'freeze': 'توقف عضویت', 'plan_change': 'تغییر طرح', 'coach_change': 'تغییر مربی',
    'payment': 'پیگیری پرداخت', 'schedule': 'تغییر زمان جلسه', 'identity': 'اصلاح اطلاعات حساب',
    'general': 'پشتیبانی عمومی', 'coach_contact': 'تماس با مربی', 'renewal': 'تمدید عضویت',
}


def member_endpoint(methods):
    def decorate(function):
        @never_cache
        @require_http_methods(methods)
        @wraps(function)
        def wrapped(request, *args, **kwargs):
            user = request.user
            if not user.is_authenticated:
                return error('برای ادامه وارد حساب شوید.', status=401)
            if user.role != User.Role.MEMBER or not user.is_active or user.status != User.Status.ACTIVE:
                return error('دسترسی عضو فعال لازم است.', status=403)
            try:
                return function(request, *args, **kwargs)
            except ValidationError as exc:
                return error(' '.join(exc.messages))
        return wrapped
    return decorate


def member_record(user):
    application = getattr(user, 'membership_application', None)
    gym = None
    if application and application.legacy_member_id:
        # Do not even select biometric columns.
        gym = LegacyMember.objects.filter(pk=application.legacy_member_id).values(
            'id', 'plan', 'signup_time', 'used_sessions', 'debt', 'age', 'gender').first()
    return application, gym


def payment_rows(gym_id):
    if not gym_id:
        return [], False
    if settings.FITTRACK_REMOTE_SYNC:
        return [{**row.data, 'id': row.local_id} for row in GymSyncRecord.objects.filter(kind='renewal', data__member_id=gym_id).order_by('-local_id')], True
    try:
        uri = settings.FITTRACK_ATTENDANCE_PATH.resolve().as_uri() + '?mode=ro'
        with closing(sqlite3.connect(uri, uri=True, timeout=5)) as conn:
            conn.row_factory = sqlite3.Row
            rows = [dict(row) for row in conn.execute(
                'SELECT id,new_plan,paid_amount,payment_reference,renewed_at,membership_started_at FROM membership_renewals '
                'WHERE member_id=? ORDER BY renewed_at DESC,id DESC', [gym_id])]
        return rows, True
    except (OSError, sqlite3.Error):
        return [], False


def payments_for(user, application, gym):
    rows, available = payment_rows(gym['id'] if gym else None)
    result = [dict(id=str(r.get('id') or r.get('local_id') or index), plan=r.get('new_plan', ''),
                   amount=max(0, int(r.get('paid_amount') or 0)), reference=r.get('payment_reference', ''),
                   date=r.get('renewed_at'), membershipStart=r.get('membership_started_at'), method='ثبت‌شده در پذیرش', status='registered')
              for index, r in enumerate(rows)]
    if application and application.paid_amount and application.activated_at:
        result.append(dict(id='application', plan=application.plan.name, amount=application.paid_amount,
                           reference='', date=application.activated_at.isoformat(), method='ثبت‌شده در پذیرش', status='registered'))
    return result, available


def normalized_days(program):
    if not program:
        return []
    result = []
    for day in program_data(program)['days']:
        movements = day.get('exercises') or []
        if not movements:
            for line in day.get('movements', []):
                match = re.match(r'^(.*?)\s*\|\s*(\d+)\s*[×x]\s*(.+)$', line)
                movements.append(dict(name=match[1].strip() if match else line,
                                      sets=int(match[2]) if match else 1, reps=match[3] if match else '',
                                      rest=None, weight=None, rpe=None, rir=None, note=''))
        result.append(dict(weekday=day.get('weekday', 'unspecified'), label=day.get('label', 'تمرین'), exercises=movements))
    return result


def workout_data(row):
    return dict(id=row.pk, programId=row.program_id, programTitle=row.program_title, trainingDay=row.training_day,
                dayIndex=row.day_index, exercises=row.exercises, note=row.personal_note,
                startedAt=row.started_at.isoformat(), finishedAt=row.finished_at.isoformat() if row.finished_at else None)


def request_data(row):
    return dict(id=row.pk, kind=row.kind, title=REQUEST_KINDS.get(row.kind, row.kind), message=row.message,
                status=row.status, reply=row.reply, createdAt=row.created_at.isoformat())


def build_workspace(user):
    application, gym = member_record(user)
    today = timezone.localdate()
    program = WorkoutProgram.objects.filter(member=user, archived_at=None).select_related('coach__coach_profile').first()
    days = normalized_days(program)
    day_index = next((i for i, d in enumerate(days) if d['weekday'] == today.strftime('%A').lower()), None)
    last_workout = MemberWorkout.objects.filter(member=user, program=program, finished_at__isnull=False).first() if program else None
    next_day = day_index if day_index is not None else (last_workout.day_index + 1) % len(days) if days and last_workout else 0
    plan = gym['plan'] if gym else application.plan.name if application else ''
    used = max(0, gym['used_sessions'] or 0) if gym else None
    # The desktop plan string is authoritative for existing memberships.
    included = session_allowance(plan) if gym else None
    remaining = max(0, included - used) if included is not None and used is not None else None
    expires, days_left, status = None, None, 'unknown'
    if gym:
        try:
            expiry_text = membership_expires_at(gym['signup_time'])
            expires = calendar_date(expiry_text).isoformat()
            days_left = (calendar_date(expiry_text) - today).days
            status = 'expired' if membership_expired(gym['signup_time'], timezone.localtime().replace(tzinfo=None)) or remaining == 0 else 'active'
        except (ValueError, OverflowError, AttributeError):
            pass
    if remaining == 0:
        status = 'expired'
    history, attendance_available = attendance_for([gym['id']]) if gym else ({}, False)
    visits = history.get(gym['id'], []) if gym else []
    jy, jm, _ = gregorian_to_jalali(today.year, today.month, today.day)
    month_start = calendar_date(f'{jy:04d}-{jm:02d}-01')
    week_start = today - timedelta(days=(today.weekday() + 2) % 7)
    this_month = sum(bool((day := calendar_date(v['checkIn'])) and month_start <= day <= today) for v in visits)
    this_week = sum(bool((day := calendar_date(v['checkIn'])) and week_start <= day <= today) for v in visits)
    sessions = [dict(id=s.pk, coachName=s.coach.get_full_name().strip() or 'مربی', programTitle=s.program_title,
                     trainingDay=s.training_day, date=s.scheduled_at.isoformat(), duration=s.duration_minutes,
                     status=s.status, group=s.group_label)
                for s in TrainingSession.objects.filter(member=user).select_related('coach').order_by('-scheduled_at')[:200]]
    payments, payments_available = payments_for(user, application, gym)
    face_registered = bool(application and application.face_registered)
    if settings.FITTRACK_REMOTE_SYNC and gym:
        device_status = GymSyncRecord.objects.filter(kind='member', local_id=gym['id']).values_list('data', flat=True).first()
        if device_status is not None:
            face_registered = device_status.get('face_registered') is True
    membership_history = []
    for payment in payments:
        if payment['id'] == 'application':
            continue
        try:
            end = calendar_date(membership_expires_at(str(payment.get('membershipStart') or payment['date'])[:19]))
        except (ValueError, OverflowError):
            end = None
        membership_history.append(dict(plan=payment['plan'], startsAt=payment.get('membershipStart') or payment['date'],
                                       endsAt=end.isoformat() if end else None,
                                       sessions=session_allowance(payment['plan']), status='registered'))
    preferences = getattr(user, 'member_preferences', None)
    notifications = []
    if days_left is not None and days_left <= 7:
        notifications.append(dict(id=f'expiry:{expires}', title='زمان تمدید عضویت', description='تاریخ اعتبار عضویت را بررسی کنید.', view='membership'))
    if remaining is not None and remaining <= 2:
        notifications.append(dict(id=f'sessions:{remaining}:{gym["signup_time"]}', title='جلسات باقی‌مانده محدود است', description=f'{remaining} جلسه باقی مانده است.', view='membership'))
    if program:
        notifications.append(dict(id=f'program:{program.pk}:{program.updated_at.isoformat()}', title='برنامه تمرینی شما به‌روز است', description=program.title, view='program'))
    if payments:
        payment = payments[0]
        notifications.append(dict(id=f'payment:{payment["id"]}', title='پرداخت شما ثبت شده است', description=payment['plan'], view='payments'))
    answered = MemberRequest.objects.filter(member=user, kind='coach_contact').exclude(reply='').first()
    if answered:
        notifications.append(dict(id=f'request:{answered.pk}:{answered.updated_at.isoformat()}', title='درخواست شما پاسخ داده شد', description=answered.reply, view='coach'))
    upcoming = sorted([s for s in sessions if s['status'] == 'scheduled' and s['date'] >= timezone.now().isoformat()], key=lambda s: s['date'])
    if upcoming:
        notifications.append(dict(id=f'session:{upcoming[0]["id"]}', title='جلسه پیش روی شما', description=upcoming[0]['trainingDay'] or upcoming[0]['programTitle'], view='sessions'))
    for item in notifications:
        item['read'] = bool(preferences and item['id'] in preferences.read_notifications)
    coach = None
    if program:
        profile = getattr(program.coach, 'coach_profile', None)
        coach = dict(name=program.coach.get_full_name().strip() or 'مربی', specialty=profile.specialty if profile else '',
                     bio=profile.bio if profile else '', notes=program.coach_notes)
    library = Exercise.objects.filter(coach__isnull=True)
    if program:
        library = Exercise.objects.filter(coach__isnull=True) | Exercise.objects.filter(coach=program.coach)
    media = {e.name: e.media_url for e in library if e.media_url.startswith(('https://', 'http://'))}
    data = dict(ok=True, user=dict(fullName=user.get_full_name().strip() or 'ورزشکار', mobile=user.mobile,
                                  nationalId=user.national_id, address=user.address,
                                  age=gym['age'] if gym else None, gender=gym['gender'] if gym else None),
                today=today.isoformat(), membership=dict(plan=plan, status=status, included=included, used=used,
                    remaining=remaining, startsAt=gym['signup_time'] if gym else None, expiresAt=expires, daysLeft=days_left,
                    faceRegistered=face_registered),
                program={**program_data(program), 'coachName': coach['name'], 'days': days} if program else None,
                todayDay=day_index, nextDay=next_day, coach=coach, media=media,
                attendance=dict(available=attendance_available, visits=visits[:100], total=len(visits), month=this_month, week=this_week),
                sessions=sessions, payments=payments, membershipHistory=membership_history,
                paymentsAvailable=payments_available, balance=gym['debt'] if gym else None,
                workouts=[workout_data(w) for w in MemberWorkout.objects.filter(member=user)[:100]],
                requests=[request_data(r) for r in MemberRequest.objects.filter(member=user)[:100]],
                notifications=notifications, notificationsEnabled=preferences.notifications_enabled if preferences else True)
    return data


@member_endpoint(['GET'])
def workspace(request):
    return JsonResponse(build_workspace(request.user))


@member_endpoint(['POST'])
def start_workout(request):
    data = payload(request)
    with transaction.atomic():
        User.objects.select_for_update().get(pk=request.user.pk)
        existing = MemberWorkout.objects.filter(member=request.user, finished_at=None).first()
        if existing:
            return JsonResponse(dict(ok=True, workout=workout_data(existing)))
        program = WorkoutProgram.objects.filter(member=request.user, archived_at=None).first()
        days = normalized_days(program)
        if not days:
            return error('ابتدا باید مربی برای شما برنامه ثبت کند.', status=409)
        index = number(data.get('dayIndex'), 0, len(days) - 1, integer=True)
        for exercise in days[index]['exercises']:
            number(exercise.get('sets', 1), 1, 10, integer=True)
        exercises = [dict(name=e['name'], prescription=e, skipped=False,
                          sets=[dict(weight=e.get('weight'), reps=None, complete=False) for _ in range(e.get('sets', 1))])
                     for e in days[index]['exercises']]
        row = MemberWorkout.objects.create(member=request.user, coach=program.coach, program=program,
                                           program_title=program.title, training_day=days[index]['label'], day_index=index, exercises=exercises)
    return JsonResponse(dict(ok=True, workout=workout_data(row)), status=201)


@member_endpoint(['PATCH'])
def workout_detail(request, workout_id):
    data = payload(request)
    with transaction.atomic():
        row = MemberWorkout.objects.select_for_update().filter(pk=workout_id, member=request.user).first()
        if not row:
            return error('تمرین پیدا نشد.', status=404)
        if row.finished_at:
            return error('این تمرین پایان یافته است.', status=409)
        if 'note' in data:
            row.personal_note = text(data['note'], 3000)
        if 'exercises' in data:
            incoming = data['exercises']
            if not isinstance(incoming, list) or len(incoming) != len(row.exercises):
                raise ValidationError('ساختار برنامه مربی قابل تغییر نیست.')
            for original, logged in zip(row.exercises, incoming):
                if not isinstance(logged, dict) or not isinstance(logged.get('skipped', False), bool):
                    raise ValidationError('اطلاعات حرکت معتبر نیست.')
                sets = logged.get('sets')
                if not isinstance(sets, list) or len(sets) != len(original['sets']):
                    raise ValidationError('تعداد ست‌های برنامه قابل تغییر نیست.')
                cleaned = []
                for s in sets:
                    if not isinstance(s, dict) or not isinstance(s.get('complete'), bool):
                        raise ValidationError('اطلاعات ست معتبر نیست.')
                    weight = number(s.get('weight'), 0, 1000, optional=True)
                    reps = number(s.get('reps'), 1, 1000, integer=True, optional=True)
                    if s['complete'] and (weight is None or reps is None):
                        raise ValidationError('وزن و تکرار ست انجام‌شده را وارد کنید.')
                    cleaned.append(dict(weight=weight, reps=reps, complete=s['complete']))
                original.update(sets=cleaned, skipped=logged.get('skipped', False))
        if data.get('finish') is True:
            # Members finish the session without entering individual set results.
            row.finished_at = timezone.now()
        row.save(update_fields=['personal_note', 'exercises', 'finished_at'])
    return JsonResponse(dict(ok=True, workout=workout_data(row)))


@member_endpoint(['POST'])
def support(request):
    data = payload(request)
    kind = data.get('kind')
    if kind not in REQUEST_KINDS:
        raise ValidationError('نوع درخواست معتبر انتخاب کنید.')
    message = text(data.get('message', ''), 3000, required=True)
    row = MemberRequest.objects.create(member=request.user, kind=kind, message=message)
    return JsonResponse(dict(ok=True, request=request_data(row)), status=201)


@member_endpoint(['PATCH'])
def preferences(request):
    data = payload(request)
    with transaction.atomic():
        User.objects.select_for_update().get(pk=request.user.pk)
        row, _ = MemberPreferences.objects.get_or_create(member=request.user)
        if 'notificationsEnabled' in data:
            if not isinstance(data['notificationsEnabled'], bool):
                raise ValidationError('تنظیم اعلان معتبر نیست.')
            row.notifications_enabled = data['notificationsEnabled']
        if 'read' in data:
            ids = data['read']
            if not isinstance(ids, list) or len(ids) > 30 or any(not isinstance(i, str) or len(i) > 200 for i in ids):
                raise ValidationError('اعلان‌ها معتبر نیستند.')
            row.read_notifications = list(dict.fromkeys([*row.read_notifications, *ids]))[-100:]
        row.save()
    return JsonResponse(dict(ok=True))


@member_endpoint(['POST'])
def account(request):
    data = payload(request)
    user = request.user
    if data.get('action') == 'password':
        current = data.get('currentPassword')
        password = data.get('newPassword')
        if not isinstance(current, str) or not isinstance(password, str) or not 1 <= len(current) <= 256 or not 1 <= len(password) <= 256:
            raise ValidationError('رمز عبور معتبر وارد کنید.')
        if not user.check_password(current):
            raise ValidationError('رمز عبور فعلی درست نیست.')
        validate_password(password, user)
        user.set_password(password)
        user.save(update_fields=['password'])
        update_session_auth_hash(request, user)
    elif data.get('action') == 'logout_others':
        for session in Session.objects.filter(expire_date__gt=timezone.now()).exclude(session_key=request.session.session_key).iterator():
            if str(session.get_decoded().get('_auth_user_id')) == str(user.pk):
                session.delete()
    else:
        raise ValidationError('عملیات حساب معتبر نیست.')
    return JsonResponse(dict(ok=True))


@member_endpoint(['GET'])
def receipt(request, receipt_id):
    application, gym = member_record(request.user)
    rows, _ = payments_for(request.user, application, gym)
    row = next((p for p in rows if p['id'] == receipt_id), None)
    if not row:
        return error('رسید پیدا نشد.', status=404)
    content = f"LifeBox | رسید پرداخت\nنام: {request.user.get_full_name()}\nطرح: {row['plan']}\nمبلغ: {row['amount']:,} تومان\nتاریخ: {row['date']}\nمرجع: {row['reference'] or 'ثبت پذیرش'}\n"
    response = HttpResponse(content, content_type='text/plain; charset=utf-8')
    response['Content-Disposition'] = f'attachment; filename="lifebox-receipt-{receipt_id}.txt"'
    return response
