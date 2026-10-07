"""Coach-only training workspace. Explicit serializers never expose administrative data."""
import json
import math
import sqlite3
from collections import Counter, defaultdict
from contextlib import closing
from datetime import date, datetime, timedelta
from functools import wraps

from django.conf import settings
from django.core.exceptions import ValidationError
from django.db import transaction
from django.db.models import Q
from django.http import JsonResponse
from django.utils import timezone
from django.views.decorators.http import require_http_methods
from django.views.decorators.cache import never_cache

from app.domain.dates import membership_expires_at, membership_expired
from app.domain.membership import remaining_sessions
from .insights import calendar_date
from .models import (Assessment, CoachNote, Exercise, GymSyncCursor, GymSyncRecord,
                     LegacyMember, ProgramRevision, TrainingProfile, TrainingSession, User, WorkoutProgram)
from .views import _coach_member_queryset, _is_coach, _program_payload, error, public_coach

GOALS = {'muscle_gain', 'fat_loss', 'strength', 'recomposition', 'fitness'}
MUSCLES = {'chest', 'back', 'shoulders', 'arms', 'legs', 'core', 'full_body'}
MEASUREMENTS = {'weight': 500, 'height': 250, 'body_fat': 100, 'waist': 300,
                'chest': 300, 'arms': 150, 'thighs': 200, 'bench_press': 1000,
                'squat': 1000, 'deadlift': 1000, 'pull_ups': 1000}


def coach_endpoint(methods):
    def decorate(function):
        @never_cache
        @require_http_methods(methods)
        @wraps(function)
        def wrapped(request, *args, **kwargs):
            if not _is_coach(request.user) or not request.user.is_active:
                return error('دسترسی مربی فعال لازم است.', status=403)
            try:
                return function(request, *args, **kwargs)
            except ValidationError as exc:
                return error(' '.join(exc.messages))
        return wrapped
    return decorate


def payload(request):
    try:
        value = json.loads(request.body)
    except (ValueError, UnicodeDecodeError):
        raise ValidationError('اطلاعات درخواست معتبر نیست.')
    if not isinstance(value, dict):
        raise ValidationError('اطلاعات درخواست معتبر نیست.')
    return value


def text(value, limit=3000, required=False):
    if not isinstance(value, str) or len(value) > limit or (required and not value.strip()):
        raise ValidationError('متن خالی یا بیش از حد طولانی است.')
    return value.strip()


def number(value, minimum=0, maximum=1000, integer=False, optional=False):
    if optional and value in (None, ''):
        return None
    try:
        if isinstance(value, bool):
            raise ValueError
        result = float(value)
        if not math.isfinite(result) or not minimum <= result <= maximum or (integer and result != int(result)):
            raise ValueError
        return int(result) if integer else round(result, 2)
    except (TypeError, ValueError, OverflowError):
        raise ValidationError(f'عدد باید بین {minimum} و {maximum} باشد.')


def day(value, optional=False):
    if optional and not value:
        return None
    try:
        return date.fromisoformat(str(value))
    except (ValueError, TypeError):
        raise ValidationError('تاریخ معتبر انتخاب کنید.')


def flag(value):
    if not isinstance(value, bool):
        raise ValidationError('وضعیت انتخاب‌شده معتبر نیست.')
    return value


def member_for(request, member_id):
    return _coach_member_queryset(request.user).filter(pk=member_id).first()


def attendance_for(member_ids):
    """Filter at the source and return only training-relevant visit fields."""
    if not member_ids:
        return {}, False
    if settings.FITTRACK_REMOTE_SYNC:
        cursor = GymSyncCursor.objects.first()
        available = bool(cursor and cursor.sequence)
        rows = GymSyncRecord.objects.filter(kind='attendance', data__member_id__in=member_ids).values_list('data', flat=True)
    else:
        try:
            uri = settings.FITTRACK_ATTENDANCE_PATH.resolve().as_uri() + '?mode=ro'
            with closing(sqlite3.connect(uri, uri=True, timeout=5)) as conn:
                conn.row_factory = sqlite3.Row
                placeholders = ','.join('?' for _ in member_ids)
                rows = [dict(row) for row in conn.execute(
                    'SELECT member_id, checked_in_at, checked_out_at FROM attendance_sessions '
                    f'WHERE member_id IN ({placeholders}) ORDER BY checked_in_at DESC', list(member_ids))]
            available = True
        except (sqlite3.Error, OSError):
            return {}, False
    result = defaultdict(list)
    for row in rows:
        result[row.get('member_id')].append({'checkIn': row.get('checked_in_at'), 'checkOut': row.get('checked_out_at')})
    for visits in result.values():
        visits.sort(key=lambda visit: (calendar_date(visit['checkIn']) or date.min, str(visit['checkIn'] or '')[11:19]), reverse=True)
    return result, available


def assessment_data(item):
    return dict(id=item.pk, date=item.measured_on.isoformat(),
                **{key: float(getattr(item, key)) if getattr(item, key) is not None else None for key in MEASUREMENTS},
                fitness_notes=item.fitness_notes, mobility_notes=item.mobility_notes, strength_notes=item.strength_notes)


def profile_data(item):
    fields = ('main_goal', 'experience', 'frequency', 'preferred_style', 'limitations', 'injuries', 'notes', 'reported_pain')
    return {key: getattr(item, key) for key in fields} if item else {}


def session_data(item):
    return dict(id=item.pk, memberId=item.member_id, memberName=item.member.get_full_name().strip() or 'ورزشکار',
                programId=item.program_id, programTitle=item.program_title, trainingDay=item.training_day,
                scheduledAt=item.scheduled_at.isoformat(), durationMinutes=item.duration_minutes,
                groupLabel=item.group_label, exercises=item.exercises, status=item.status, notes=item.notes,
                completedAt=item.completed_at.isoformat() if item.completed_at else None)


def note_data(item):
    return dict(id=item.pk, memberId=item.member_id, memberName=item.member.get_full_name().strip() or 'ورزشکار',
                coachName=item.coach.get_full_name().strip() or 'مربی', sessionId=item.session_id,
                content=item.content, followUpOn=item.follow_up_on.isoformat() if item.follow_up_on else None,
                resolved=item.resolved, reportedPain=item.reported_pain, createdAt=item.created_at.isoformat())


def program_data(item):
    result = _program_payload(item)
    result.update(memberId=item.member_id, memberName=item.member.get_full_name().strip() or 'ورزشکار',
                  mainGoal=item.main_goal, startDate=item.start_date.isoformat() if item.start_date else None,
                  endDate=item.end_date.isoformat() if item.end_date else None, notes=item.coach_notes,
                  archived=bool(item.archived_at))
    return result


def save_revision(program):
    ProgramRevision.objects.create(program=program, snapshot=program_data(program))


def client_directory(coach):
    members = list(_coach_member_queryset(coach))
    legacy_ids = [m.membership_application.legacy_member_id for m in members if m.membership_application.legacy_member_id]
    legacy = {row.pk: row for row in LegacyMember.objects.filter(pk__in=legacy_ids).only(
        'id', 'age', 'gender', 'plan', 'used_sessions', 'signup_time')}
    visits, available = attendance_for(legacy_ids)
    profiles = {item.member_id: item for item in TrainingProfile.objects.filter(coach=coach, member__in=members)}
    programs = {item.member_id: item for item in WorkoutProgram.objects.filter(coach=coach, member__in=members, archived_at=None)}
    latest = {}
    for item in Assessment.objects.filter(coach=coach, member__in=members):
        latest.setdefault(item.member_id, item)
    pending = defaultdict(list)
    for note in CoachNote.objects.filter(coach=coach, member__in=members, resolved=False):
        if note.reported_pain or (note.follow_up_on and note.follow_up_on <= timezone.localdate()):
            pending[note.member_id].append(note)
    today = timezone.localdate()
    directory = []
    for member in members:
        app = member.membership_application
        gym = legacy.get(app.legacy_member_id)
        plan = gym.plan if gym else app.plan.name
        used = max(0, gym.used_sessions or 0) if gym else 0
        remaining = remaining_sessions(plan, used)
        if remaining is None and app.plan.sessions_per_month:
            remaining = app.plan.sessions_per_month - used
        joined = gym.signup_time if gym else (app.activated_at or app.requested_at).isoformat()
        try:
            expires = calendar_date(membership_expires_at(joined[:19]))
            expired = membership_expired(joined[:19], timezone.localtime().replace(tzinfo=None))
        except (ValueError, OverflowError):
            expires = None
            expired = False
        days_left = (expires - today).days if expires else None
        status = 'expired' if expired or (remaining is not None and remaining <= 0) else 'expiring' if days_left is not None and days_left <= 7 else 'active'
        history = visits.get(app.legacy_member_id, [])
        last_date = calendar_date(history[0]['checkIn']) if history else None
        absent = (today - last_date).days if last_date else None
        recent = sum(bool((d := calendar_date(v['checkIn'])) and today - timedelta(days=14) <= d <= today) for v in history)
        previous = sum(bool((d := calendar_date(v['checkIn'])) and today - timedelta(days=28) <= d < today - timedelta(days=14)) for v in history)
        profile, program, assessment = profiles.get(member.pk), programs.get(member.pk), latest.get(member.pk)
        alerts = []
        def alert(kind, message, severity='warning'):
            alerts.append(dict(kind=kind, message=message, severity=severity))
        if absent is not None and absent >= 7 and available:
            alert('inactive', f'{absent} روز از آخرین حضور گذشته', 'danger' if absent >= 14 else 'warning')
        if available and previous >= 3 and recent < previous / 2:
            alert('attendance_drop', 'حضور در دو هفته اخیر کاهش یافته')
        if remaining is not None and remaining <= 2:
            alert('low_sessions', f'{max(0, remaining)} جلسه باقی‌مانده', 'danger' if remaining <= 0 else 'warning')
        if status == 'expired':
            alert('expired', 'عضویت یا سهمیه جلسات پایان یافته', 'danger')
        elif days_left is not None and days_left <= 7:
            alert('expiring', f'عضویت تا {days_left} روز دیگر پایان می‌یابد')
        end = program.end_date if program else None
        if program and not end:
            end = (program.start_date or timezone.localtime(program.updated_at).date()) + timedelta(weeks=program.duration_weeks)
        if not program or (end and end <= today + timedelta(days=7)):
            alert('program', 'برنامه تمرینی نیاز به به‌روزرسانی دارد' if program else 'برنامه تمرینی ثبت نشده')
        if not assessment or (today - assessment.measured_on).days >= 30:
            alert('assessment', 'ارزیابی ماهانه موعد رسیده' if assessment else 'ارزیابی اولیه نیاز است', 'info')
        if (profile and profile.reported_pain) or any(n.reported_pain for n in pending[member.pk]):
            alert('pain', 'درد یا ناراحتی گزارش شده', 'danger')
        if any(n.follow_up_on and n.follow_up_on <= today for n in pending[member.pk]):
            alert('follow_up', 'پیگیری مربی موعد رسیده')
        directory.append(dict(id=member.pk, fullName=member.get_full_name().strip() or 'ورزشکار',
                              age=gym.age if gym else None, gender=gym.gender if gym else app.plan.gender,
                              plan=plan, trainingStyle='semi_private' if 'نیمه' in plan else 'private' if 'خصوصی' in plan else 'general',
                              status=status, membershipStart=joined, expiresAt=expires.isoformat() if expires else None,
                              sessionsUsed=used, sessionsRemaining=max(0, remaining) if remaining is not None else None,
                              lastVisit=history[0]['checkIn'] if history else None, daysAbsent=absent,
                              faceRegistered=app.face_registered, mainGoal=profile.main_goal if profile else '',
                              isNew=not assessment, profile=profile_data(profile),
                              currentProgram=program_data(program) if program else None,
                              lastAssessment=assessment_data(assessment) if assessment else None, alerts=alerts))
    return directory, visits, available


@coach_endpoint(['GET'])
def workspace(request):
    clients, _, available = client_directory(request.user)
    ids = [c['id'] for c in clients]
    sessions = TrainingSession.objects.filter(coach=request.user, member_id__in=ids).select_related('member')
    today = timezone.localdate()
    todays = list(sessions.filter(scheduled_at__date=today))
    relevant = [s for s in todays if s.status not in {'cancelled', 'no_show'}]
    metrics = dict(activeClients=sum(c['status'] != 'expired' for c in clients),
                   trainingToday=len({s.member_id for s in relevant}), sessionsToday=len(relevant),
                   programsDue=sum(any(a['kind'] == 'program' for a in c['alerts']) for c in clients),
                   assessmentsDue=sum(any(a['kind'] == 'assessment' for a in c['alerts']) for c in clients),
                   followUps=sum(any(a['kind'] in {'inactive', 'attendance_drop', 'pain', 'follow_up'} for a in c['alerts']) for c in clients),
                   lowSessions=sum(any(a['kind'] == 'low_sessions' for a in c['alerts']) for c in clients))
    monthly = sessions.filter(scheduled_at__date__gte=today.replace(day=1), scheduled_at__date__lte=today)
    counts = Counter(monthly.values_list('status', flat=True))
    valid = [c for c in clients if c['status'] != 'expired']
    retention_base = [c for c in clients if (calendar_date(c['membershipStart']) or today) < today.replace(day=1)]
    performance = dict(sessionsMonth=monthly.count(), completed=counts['completed'], cancelled=counts['cancelled'],
                       noShow=counts['no_show'], activeClients=len(valid),
                       newClients=sum((calendar_date(c['membershipStart']) or date.min) >= today.replace(day=1) for c in clients),
                       attendanceRate=round(100 * sum(c['daysAbsent'] is not None and c['daysAbsent'] < 7 for c in valid) / len(valid)) if valid and available else None,
                       retention=round(100 * sum(c['status'] != 'expired' for c in retention_base) / len(retention_base)) if retention_base else None)
    return JsonResponse(dict(ok=True, coach=public_coach(request.user), clients=clients, metrics=metrics,
                             today=today.isoformat(), todaySessions=[session_data(s) for s in todays],
                             attendanceAvailable=available, performance=performance))


@coach_endpoint(['GET', 'PATCH'])
def client_detail(request, member_id):
    member = member_for(request, member_id)
    if not member:
        return error('ورزشکار در دسترسی شما نیست.', status=404)
    if request.method == 'PATCH':
        data = payload(request)
        goal = data.get('main_goal', '')
        experience = data.get('experience', '')
        if goal not in GOALS or experience not in {'beginner', 'intermediate', 'advanced'}:
            raise ValidationError('هدف و سطح تجربه را انتخاب کنید.')
        values = dict(main_goal=goal, experience=experience, frequency=number(data.get('frequency', 3), 1, 7, integer=True),
                      reported_pain=flag(data.get('reported_pain', False)))
        for key in ('preferred_style', 'limitations', 'injuries', 'notes'):
            values[key] = text(data.get(key, ''), 160 if key == 'preferred_style' else 3000)
        TrainingProfile.objects.update_or_create(coach=request.user, member=member, defaults=values)
    clients, visits, available = client_directory(request.user)
    client = next(c for c in clients if c['id'] == member_id)
    assessments = [assessment_data(a) for a in Assessment.objects.filter(coach=request.user, member=member)]
    comparisons = {key: round(assessments[0][key] - assessments[1][key], 2)
                   for key in MEASUREMENTS if len(assessments) > 1 and assessments[0][key] is not None and assessments[1][key] is not None}
    history = []
    program = WorkoutProgram.objects.filter(coach=request.user, member=member).first()
    if program:
        history = [dict(id=r.pk, savedAt=r.created_at.isoformat(), program=r.snapshot) for r in program.revisions.all()]
        if program.archived_at:
            history.insert(0, dict(id=0, savedAt=program.archived_at.isoformat(), program=program_data(program)))
    attendance = visits.get(member.membership_application.legacy_member_id, [])
    return JsonResponse(dict(ok=True, client=client, assessments=assessments, comparison=comparisons,
                             programHistory=history, notes=[note_data(n) for n in CoachNote.objects.filter(coach=request.user, member=member).select_related('coach', 'member')],
                             sessions=[session_data(s) for s in TrainingSession.objects.filter(coach=request.user, member=member).select_related('member').order_by('-scheduled_at')],
                             attendance=attendance[:100], visitCount=len(attendance), attendanceAvailable=available))


@coach_endpoint(['POST'])
def assessments(request):
    data = payload(request)
    member = member_for(request, number(data.get('memberId'), 1, 2**31, integer=True))
    if not member:
        return error('ورزشکار در دسترسی شما نیست.', status=404)
    measured = day(data.get('date'))
    if measured > timezone.localdate():
        raise ValidationError('ارزیابی نمی‌تواند در آینده باشد.')
    values = {key: number(data.get(key), 0, maximum, integer=key == 'pull_ups', optional=True) for key, maximum in MEASUREMENTS.items()}
    if not any(value is not None for value in values.values()):
        raise ValidationError('حداقل یک اندازه‌گیری وارد کنید.')
    for key in ('fitness_notes', 'mobility_notes', 'strength_notes'):
        values[key] = text(data.get(key, ''))
    item = Assessment.objects.create(coach=request.user, member=member, measured_on=measured, **values)
    return JsonResponse(dict(ok=True, assessment=assessment_data(item)), status=201)


@coach_endpoint(['GET', 'POST'])
def notes(request):
    if request.method == 'GET':
        rows = CoachNote.objects.filter(coach=request.user, member__in=_coach_member_queryset(request.user)).select_related('member', 'coach')
        return JsonResponse(dict(ok=True, notes=[note_data(n) for n in rows]))
    data = payload(request)
    member = member_for(request, number(data.get('memberId'), 1, 2**31, integer=True))
    if not member:
        return error('ورزشکار در دسترسی شما نیست.', status=404)
    session = None
    if data.get('sessionId'):
        session = TrainingSession.objects.filter(pk=number(data['sessionId'], 1, 2**31, integer=True), coach=request.user, member=member).first()
        if not session:
            raise ValidationError('جلسه مرتبط معتبر نیست.')
    item = CoachNote.objects.create(coach=request.user, member=member, session=session,
                                    content=text(data.get('content', ''), required=True),
                                    follow_up_on=day(data.get('followUpOn'), optional=True),
                                    reported_pain=flag(data.get('reportedPain', False)))
    return JsonResponse(dict(ok=True, note=note_data(item)), status=201)


@coach_endpoint(['PATCH'])
def note_detail(request, note_id):
    item = CoachNote.objects.filter(pk=note_id, coach=request.user, member__in=_coach_member_queryset(request.user)).first()
    if not item:
        return error('یادداشت پیدا نشد.', status=404)
    item.resolved = flag(payload(request).get('resolved'))
    item.save(update_fields=['resolved'])
    return JsonResponse(dict(ok=True))


def normalize_exercise(data, logging=False):
    if not isinstance(data, dict):
        raise ValidationError('اطلاعات حرکت معتبر نیست.')
    item = dict(name=text(data.get('name', ''), 160, required=True),
                rest=number(data.get('rest', 90), 0, 600, integer=True),
                rpe=number(data.get('rpe'), 1, 10, optional=True),
                rir=number(data.get('rir'), 0, 10, optional=True),
                tempo=text(data.get('tempo', ''), 40), note=text(data.get('note', ''), 500))
    if logging:
        sets = data.get('sets')
        if not isinstance(sets, list) or not 1 <= len(sets) <= 10:
            raise ValidationError('برای هر حرکت بین ۱ تا ۱۰ ست وارد کنید.')
        item.update(skipped=flag(data.get('skipped', False)), sets=[
            dict(weight=number(s.get('weight'), 0, 1000, optional=True),
                 reps=number(s.get('reps'), 0, 1000, integer=True, optional=True),
                 complete=flag(s.get('complete', False))) if isinstance(s, dict) else None for s in sets])
        if None in item['sets'] or any(s['complete'] and (s['weight'] is None or s['reps'] is None or s['reps'] < 1) for s in item['sets']):
            raise ValidationError('وزن و تکرار ست‌های انجام‌شده را وارد کنید.')
    else:
        item.update(sets=number(data.get('sets', 3), 1, 10, integer=True),
                    reps=text(str(data.get('reps', '10')), 40, required=True),
                    weight=number(data.get('weight'), 0, 1000, optional=True))
    return item


@coach_endpoint(['GET', 'POST'])
def programs(request):
    if request.method == 'GET':
        rows = WorkoutProgram.objects.filter(coach=request.user, member__in=_coach_member_queryset(request.user), archived_at=None).select_related('member')
        return JsonResponse(dict(ok=True, programs=[program_data(p) for p in rows]))
    data = payload(request)
    member = member_for(request, number(data.get('memberId'), 1, 2**31, integer=True))
    if not member:
        return error('ورزشکار در دسترسی شما نیست.', status=404)
    goal = data.get('mainGoal')
    if goal not in GOALS:
        raise ValidationError('هدف برنامه را انتخاب کنید.')
    start, end = day(data.get('startDate')), day(data.get('endDate'))
    if end < start:
        raise ValidationError('پایان برنامه باید پس از شروع آن باشد.')
    days = data.get('days')
    if not isinstance(days, list) or not 1 <= len(days) <= 7:
        raise ValidationError('برنامه باید بین ۱ تا ۷ روز تمرین داشته باشد.')
    cleaned = []
    weekdays = set()
    from .views import WEEKDAYS
    for item in days:
        if not isinstance(item, dict) or item.get('weekday') not in WEEKDAYS or item['weekday'] in weekdays:
            raise ValidationError('روزهای هفته معتبر و بدون تکرار انتخاب کنید.')
        weekdays.add(item['weekday'])
        exercises = item.get('exercises')
        if not isinstance(exercises, list) or not 1 <= len(exercises) <= 30:
            raise ValidationError('برای هر روز بین ۱ تا ۳۰ حرکت وارد کنید.')
        exercises = [normalize_exercise(e) for e in exercises]
        cleaned.append(dict(weekday=item['weekday'], label=text(item.get('label', WEEKDAYS[item['weekday']]), 160, required=True),
                            exercises=exercises, movements=[f"{e['name']} | {e['sets']} × {e['reps']}" for e in exercises]))
    values = dict(title=text(data.get('title', ''), 180, required=True), main_goal=goal,
                  start_date=start, end_date=end, coach_notes=text(data.get('notes', '')),
                  duration_weeks=min(12, max(1, math.ceil(((end - start).days + 1) / 7))),
                  schedule_json=cleaned, exercises='\n'.join(m for d in cleaned for m in d['movements']), archived_at=None)
    with transaction.atomic():
        User.objects.select_for_update().get(pk=request.user.pk)
        existing = WorkoutProgram.objects.select_for_update().filter(coach=request.user, member=member).first()
        if existing:
            save_revision(existing)
            for key, value in values.items():
                setattr(existing, key, value)
            existing.save()
        else:
            existing = WorkoutProgram.objects.create(coach=request.user, member=member, **values)
    return JsonResponse(dict(ok=True, program=program_data(existing)))


@coach_endpoint(['PATCH'])
def program_detail(request, program_id):
    with transaction.atomic():
        item = WorkoutProgram.objects.select_for_update().filter(pk=program_id, coach=request.user, member__in=_coach_member_queryset(request.user)).first()
        if not item:
            return error('برنامه پیدا نشد.', status=404)
        if payload(request).get('action') != 'archive':
            raise ValidationError('عملیات معتبر نیست.')
        if not item.archived_at:
            item.archived_at = timezone.now()
            item.save(update_fields=['archived_at', 'updated_at'])
    return JsonResponse(dict(ok=True))


@coach_endpoint(['GET', 'POST'])
def sessions(request):
    if request.method == 'GET':
        start = day(request.GET.get('start', timezone.localdate().isoformat()))
        end = day(request.GET.get('end', (start + timedelta(days=7)).isoformat()))
        if end < start or (end - start).days > 366:
            raise ValidationError('بازه زمانی معتبر انتخاب کنید (حداکثر یک سال).')
        rows = TrainingSession.objects.filter(coach=request.user, member__in=_coach_member_queryset(request.user),
                                              scheduled_at__date__gte=start, scheduled_at__date__lte=end).select_related('member')
        return JsonResponse(dict(ok=True, sessions=[session_data(s) for s in rows]))
    data = payload(request)
    ids = data.get('memberIds', [data.get('memberId')])
    if not isinstance(ids, list) or not 1 <= len(ids) <= 20:
        raise ValidationError('بین ۱ تا ۲۰ ورزشکار انتخاب کنید.')
    ids = {number(i, 1, 2**31, integer=True) for i in ids}
    members = list(_coach_member_queryset(request.user).filter(pk__in=ids))
    if len(members) != len(ids):
        return error('ورزشکار در دسترسی شما نیست.', status=404)
    try:
        at = datetime.fromisoformat(str(data.get('scheduledAt', '')))
        if timezone.is_naive(at):
            at = timezone.make_aware(at)
    except (ValueError, TypeError):
        raise ValidationError('تاریخ و ساعت جلسه معتبر نیست.')
    duration = number(data.get('durationMinutes', 60), 15, 240, integer=True)
    group = text(data.get('groupLabel', ''), 160)
    if len(members) > 1 and not group:
        raise ValidationError('نام گروه را وارد کنید.')
    training_day = number(data.get('dayIndex', 0), 0, 6, integer=True)
    prepared = []
    for member in members:
        program = WorkoutProgram.objects.filter(coach=request.user, member=member, archived_at=None).first()
        if not program or training_day >= len(program.schedule_json):
            raise ValidationError('ابتدا برای همه ورزشکاران برنامه و روز تمرین ثبت کنید.')
        selected = program.schedule_json[training_day]
        exercises = selected.get('exercises') or [dict(name=m, sets=1, reps='', rest=90) for m in selected.get('movements', [])]
        log = []
        for movement in exercises:
            log.append(dict(name=movement['name'], rest=movement.get('rest', 90), rpe=movement.get('rpe'), rir=movement.get('rir'),
                            tempo=movement.get('tempo', ''), note=movement.get('note', ''), skipped=False,
                            targetReps=movement.get('reps', ''), sets=[dict(weight=movement.get('weight'), reps=None, complete=False) for _ in range(movement.get('sets', 1))]))
        prepared.append(dict(coach=request.user, member=member, program=program, program_title=program.title,
                             training_day=selected.get('label', ''), scheduled_at=at, duration_minutes=duration, group_label=group, exercises=log))
    with transaction.atomic():
        # Row-locking databases serialize bookings from multiple tabs here.
        User.objects.select_for_update().get(pk=request.user.pk)
        overlap = TrainingSession.objects.filter(coach=request.user,
                                                 scheduled_at__lt=at + timedelta(minutes=duration)).exclude(status__in=['cancelled', 'no_show'])
        for existing in overlap:
            if existing.scheduled_at + timedelta(minutes=existing.duration_minutes) <= at:
                continue
            same_group = bool(group and existing.group_label == group and existing.scheduled_at == at and existing.duration_minutes == duration)
            if existing.member_id in ids or not same_group:
                raise ValidationError('این بازه با جلسه دیگری تداخل دارد؛ برای تمرین هم‌زمان یک گروه مشترک ثبت کنید.')
        created = [TrainingSession.objects.create(**values) for values in prepared]
    return JsonResponse(dict(ok=True, sessions=[session_data(s) for s in created]), status=201)


@coach_endpoint(['GET', 'PATCH'])
def session_detail(request, session_id):
    with transaction.atomic():
        item = TrainingSession.objects.select_for_update().filter(pk=session_id, coach=request.user,
                                                                  member__in=_coach_member_queryset(request.user)).select_related('member').first()
        if not item:
            return error('جلسه پیدا نشد.', status=404)
        if request.method == 'PATCH':
            data = payload(request)
            if item.status in {'completed', 'cancelled', 'no_show'}:
                raise ValidationError('این جلسه بسته شده است.')
            status = data.get('status', item.status)
            if status not in TrainingSession.Status.values or (item.status == 'in_progress' and status == 'scheduled'):
                raise ValidationError('وضعیت جلسه معتبر نیست.')
            if 'exercises' in data:
                if not isinstance(data['exercises'], list) or not 1 <= len(data['exercises']) <= 30:
                    raise ValidationError('بین ۱ تا ۳۰ حرکت ثبت کنید.')
                previous = item.exercises
                item.exercises = [normalize_exercise(e, logging=True) for e in data['exercises']]
                for index, movement in enumerate(item.exercises):
                    movement['targetReps'] = text(str(data['exercises'][index].get('targetReps', previous[index].get('targetReps', '') if index < len(previous) else '')), 40)
            item.notes = text(data.get('notes', item.notes))
            item.status = status
            if status == 'completed':
                item.completed_at = timezone.now()
            item.save()
    return JsonResponse(dict(ok=True, session=session_data(item)))


@coach_endpoint(['GET', 'POST'])
def exercises(request):
    if request.method == 'GET':
        rows = Exercise.objects.filter(Q(coach=None) | Q(coach=request.user))
        return JsonResponse(dict(ok=True, exercises=[dict(id=e.pk, name=e.name, muscleGroup=e.muscle_group,
            equipment=e.equipment, instructions=e.instructions, commonMistakes=e.common_mistakes, mediaUrl=e.media_url, custom=e.coach_id is not None) for e in rows]))
    data = payload(request)
    if data.get('muscleGroup') not in MUSCLES:
        raise ValidationError('گروه عضلانی را انتخاب کنید.')
    media = text(data.get('mediaUrl', ''), 200)
    if media:
        from django.core.validators import URLValidator
        URLValidator(schemes=['https'])(media)
    item = Exercise.objects.create(coach=request.user, name=text(data.get('name', ''), 160, required=True),
                                   muscle_group=data['muscleGroup'], equipment=text(data.get('equipment', ''), 160),
                                   instructions=text(data.get('instructions', '')), common_mistakes=text(data.get('commonMistakes', '')), media_url=media)
    return JsonResponse(dict(ok=True, exerciseId=item.pk), status=201)
