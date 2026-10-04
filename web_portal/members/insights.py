"""Read-only owner insights, using the same membership rules as reception."""
import sqlite3
from collections import Counter
from contextlib import closing
from datetime import datetime, timedelta, timezone as datetime_timezone

from django.conf import settings
from django.utils import timezone

from app.domain.dates import gregorian_to_jalali, membership_expired, membership_expires_at, validate_membership_datetime
from app.domain.membership import remaining_sessions
from .models import GymSyncCursor, GymSyncRecord


def calendar_date(value):
    """Convert a valid stored Gregorian/Jalali date to a Gregorian date."""
    if not value:
        return None
    try:
        text = str(value)
        if text[:4].isdigit() and int(text[:4]) >= 1700:
            return datetime.fromisoformat(text[:10].replace('/', '-').replace('_', '-')).date()
        normalized = validate_membership_datetime(str(value).split('+')[0].split('.')[0])
        year, month, day = map(int, normalized[:10].split('-'))
        nowruz = next(datetime(year + 621, 3, d).date() for d in range(18, 23)
                      if gregorian_to_jalali(year + 621, 3, d) == (year, 1, 1))
        offset = (month - 1) * 31 if month <= 6 else 186 + (month - 7) * 30
        return nowruz + timedelta(days=offset + day - 1)
    except (ValueError, OverflowError, StopIteration):
        return None


def records(kind):
    if settings.FITTRACK_REMOTE_SYNC:
        cursor = GymSyncCursor.objects.first()
        available = bool(cursor and cursor.sequence)
        return list(GymSyncRecord.objects.filter(kind=kind).values_list('data', flat=True)), available
    table, fields = {
        'attendance': ('attendance_sessions', 'member_id,full_name,mobile,plan,checked_in_at,checked_out_at,locker_id'),
        'renewal': ('membership_renewals', 'id,member_id,new_plan,paid_amount,payment_reference,renewed_at'),
    }[kind]
    try:
        with closing(sqlite3.connect(settings.FITTRACK_ATTENDANCE_PATH.resolve().as_uri() + '?mode=ro', uri=True, timeout=5)) as conn:
            conn.row_factory = sqlite3.Row
            return [dict(row) for row in conn.execute(f'SELECT {fields} FROM {table}')], True
    except (sqlite3.Error, OSError):
        return [], False


def build_overview(directory):
    today = timezone.localdate()
    now = datetime.combine(today, timezone.localtime().time())
    month_start = today.replace(day=1)
    visits, attendance_available = records('attendance')
    renewals, payments_available = records('renewal')
    last_visits = {}
    attendance_daily = Counter()
    hours = Counter()
    for visit in visits:
        day = calendar_date(visit.get('checked_in_at'))
        if not day:
            continue
        member_id = visit.get('member_id')
        last_visits[member_id] = max(day, last_visits.get(member_id, day))
        attendance_daily[day.isoformat()] += 1
        if day == today:
            try:
                hours[int(visit['checked_in_at'][11:13])] += 1
            except (ValueError, KeyError):
                pass

    metrics = dict(total=0, active=0, expiring=0, expired=0, unknown=0, debt=0, debtMembers=0, inactive=0, pending=0,
                   todayAttendance=attendance_daily[today.isoformat()] if attendance_available else None,
                   inside=sum(not v.get('checked_out_at') for v in visits) if attendance_available else None)
    details = []
    for member in directory:
        if member['role'] != 'member':
            continue
        metrics['total'] += 1
        detail = dict(key=member['key'], membershipStatus='unknown', expiresAt=None, daysLeft=None,
                      lastVisit=last_visits.get(member['gymId']).isoformat() if member['gymId'] in last_visits else None,
                      remainingSessions=remaining_sessions(member['plan'], member['sessionsUsed']), inactive=False)
        if not member['gymId']:
            detail['membershipStatus'] = 'pending'
            metrics['pending'] += 1
        else:
            try:
                expiry = calendar_date(membership_expires_at(member['joinedAt']))
            except (ValueError, OverflowError):
                expiry = None
            if expiry:
                days = (expiry - today).days
                detail.update(expiresAt=expiry.isoformat(), daysLeft=days)
                exhausted = detail['remainingSessions'] is not None and detail['remainingSessions'] <= 0
                status = 'expired' if membership_expired(member['joinedAt'], now) or exhausted else 'expiring' if days <= 7 else 'active'
                detail['membershipStatus'] = status
                metrics[status] += 1
            else:
                metrics['unknown'] += 1
            # A visit older than 14 days is evidence; missing history is not.
            last = last_visits.get(member['gymId'])
            if attendance_available and last and (today - last).days > 14 and detail['membershipStatus'] in {'active', 'expiring'}:
                detail['inactive'] = True
                metrics['inactive'] += 1
        if member['debt'] > 0:
            metrics['debtMembers'] += 1
            metrics['debt'] += member['debt']
        details.append(detail)

    names = {m['gymId']: m for m in directory if m['gymId']}
    payment_daily = Counter()
    payments = []
    for renewal in renewals:
        # SQLite CURRENT_TIMESTAMP is UTC; synchronized rows retain that format.
        try:
            at = datetime.fromisoformat(renewal['renewed_at'].replace('Z', '+00:00'))
            if timezone.is_naive(at):
                at = at.replace(tzinfo=datetime_timezone.utc)
            at = timezone.localtime(at)
        except (ValueError, KeyError, TypeError):
            continue
        amount = max(0, int(renewal.get('paid_amount') or 0))
        payment_daily[at.date().isoformat()] += amount
        member = names.get(renewal.get('member_id'), {})
        payments.append(dict(memberKey=member.get('key'), name=(member.get('firstName', '')+' '+member.get('lastName', '')).strip() or 'عضو پیشین',
                             amount=amount, plan=renewal.get('new_plan', ''), reference=renewal.get('payment_reference', ''), at=at.isoformat()))
    metrics['todayPayments'] = payment_daily[today.isoformat()] if payments_available else None
    metrics['monthPayments'] = sum(amount for day, amount in payment_daily.items() if month_start.isoformat() <= day <= today.isoformat()) if payments_available else None
    chart_start = today - timedelta(days=29)
    days = [chart_start + timedelta(days=i) for i in range(30)]
    return dict(ok=True, metrics=metrics, members=details, payments=sorted(payments, key=lambda p: p['at'], reverse=True)[:500],
                series=[dict(date=day.isoformat(), payments=payment_daily[day.isoformat()] if payments_available else None,
                             attendance=attendance_daily[day.isoformat()] if attendance_available else None) for day in days],
                hours=[dict(hour=hour, count=hours[hour]) for hour in range(6, 24)],
                attendanceAvailable=attendance_available, paymentsAvailable=payments_available,
                start=chart_start.isoformat(), end=today.isoformat())
