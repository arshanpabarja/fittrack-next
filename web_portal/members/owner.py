"""Owner operations share the gym member database and desktop plan catalog."""
import json
import re
import sqlite3
import tempfile
from contextlib import closing
from datetime import datetime, time, timedelta
from functools import wraps
from pathlib import Path

from django.conf import settings
from django.db import IntegrityError, transaction
from django.db.models import Q
from django.http import JsonResponse
from django.utils import timezone
from django.views.decorators.http import require_http_methods

from .models import LegacyMember, LoginEvent, MembershipApplication, OwnerAudit, Plan, User
from .views import _is_admin, _desktop_plan_payload, _desktop_plan_values, body_json, error, normalize_digits, MOBILE_RE, NATIONAL_ID_RE


def owner_only(view):
    @wraps(view)
    def wrapped(request, *args, **kwargs):
        if not _is_admin(request.user):
            return error("دسترسی فقط برای مدیر باشگاه مجاز است.", 403)
        response = view(request, *args, **kwargs)
        response['Cache-Control'] = 'no-store'
        return response
    return wrapped


def audit(request, action):
    OwnerAudit.objects.create(actor=request.user, action=action)


def member_rows():
    # Never load face images or embeddings into the owner directory.
    fields = ['id', 'first_name', 'last_name', 'mobile', 'national_id', 'address', 'plan', 'used_sessions', 'debt', 'payment', 'signup_time']
    local = {m['id']: m for m in LegacyMember.objects.values(*fields)}
    by_mobile = {normalize_digits(m['mobile']): m for m in local.values()}
    linked = set()
    rows = []
    for user in User.objects.select_related('membership_application__plan').order_by('-date_joined'):
        application = getattr(user, 'membership_application', None)
        gym = local.get(application.legacy_member_id) if application else None
        if not gym and user.role == User.Role.MEMBER:
            gym = by_mobile.get(user.mobile)
        if gym:
            linked.add(gym['id'])
        rows.append(dict(
            key=f'web:{user.id}', webId=user.id, gymId=gym['id'] if gym else None,
            firstName=user.first_name, lastName=user.last_name, mobile=user.mobile,
            nationalId=user.national_id or '', address=user.address, role=user.role,
            status=user.status, plan=gym['plan'] if gym else application.plan.name if application else '',
            joinedAt=gym['signup_time'] if gym else user.date_joined.isoformat(),
            lastLogin=user.last_login.isoformat() if user.last_login else None,
            debt=gym['debt'] or 0 if gym else 0, payment=gym['payment'] or 0 if gym else 0,
            sessionsUsed=gym['used_sessions'] or 0 if gym else 0,
        ))
    for gym in local.values():
        if gym['id'] in linked:
            continue
        rows.append(dict(key=f"gym:{gym['id']}", webId=None, gymId=gym['id'], firstName=gym['first_name'],
                         lastName=gym['last_name'], mobile=gym['mobile'], nationalId=gym['national_id'] or '',
                         address=gym['address'] or '', role='member', status='gym', plan=gym['plan'],
                         joinedAt=gym['signup_time'], lastLogin=None, debt=gym['debt'] or 0,
                         payment=gym['payment'] or 0, sessionsUsed=gym['used_sessions'] or 0))
    return rows


@owner_only
@require_http_methods(['GET'])
def members(request):
    rows = member_rows()
    search = request.GET.get('search', '').strip().casefold()[:100]
    if search:
        rows = [r for r in rows if search in (r['firstName']+' '+r['lastName']).casefold()
                or normalize_digits(search) in normalize_digits(r['mobile']) or normalize_digits(search) in r['nationalId']]
    return JsonResponse({'ok': True, 'members': rows})


@owner_only
@require_http_methods(['PATCH'])
def member(request, source, member_id):
    payload = body_json(request)
    if payload is None:
        return error('اطلاعات معتبر نیست.')
    user = User.objects.filter(pk=member_id).first() if source == 'web' else None
    gym = LegacyMember.objects.filter(pk=member_id).first() if source == 'gym' else None
    if source not in {'web', 'gym'} or (not user and not gym):
        return error('عضو پیدا نشد.', 404)
    if user and user.role == User.Role.ADMIN:
        return error('حساب مدیر از این فرم قابل تغییر نیست.', 403)
    if user:
        application = getattr(user, 'membership_application', None)
        gym = LegacyMember.objects.filter(pk=application.legacy_member_id).first() if application else None
        gym = gym or LegacyMember.objects.filter(mobile=user.mobile).first()
    elif gym:
        user = User.objects.filter(Q(membership_application__legacy_member_id=gym.id) | Q(mobile=gym.mobile)).first()
    if user and user.role == User.Role.ADMIN:
        return error('حساب مدیر از این فرم قابل تغییر نیست.', 403)
    values = {}
    for api_key, key, limit in [('firstName', 'first_name', 150), ('lastName', 'last_name', 150), ('mobile', 'mobile', 11), ('nationalId', 'national_id', 10), ('address', 'address', 2000)]:
        if api_key not in payload:
            continue
        value = str(payload[api_key]).strip()
        if key in {'mobile', 'national_id'}:
            value = normalize_digits(value)
        if len(value) > limit or (key in {'first_name', 'last_name'} and not value):
            return error('نام و مشخصات را به‌درستی وارد کنید.')
        if key == 'mobile' and not MOBILE_RE.fullmatch(value):
            return error('شماره موبایل معتبر نیست.')
        if key == 'national_id' and value and not NATIONAL_ID_RE.fullmatch(value):
            return error('کد ملی باید ده رقم باشد.')
        if key in {'mobile', 'national_id'} and value and value != normalize_digits(getattr(user or gym, key, '')):
            if User.objects.filter(**{key: value}).exclude(pk=user.pk if user else None).exists() or LegacyMember.objects.filter(**{key: value}).exclude(pk=gym.pk if gym else None).exists():
                return error('شماره موبایل یا کد ملی تکراری است.', 409)
        values[key] = value or (None if key == 'national_id' else '')
    # Changing the identity of someone checked in would break desktop checkout.
    if gym and 'mobile' in values and values['mobile'] != gym.mobile:
        try:
            with closing(attendance_connection()) as conn:
                if conn.execute('SELECT 1 FROM attendance_sessions WHERE member_id=? AND checked_out_at IS NULL', (gym.id,)).fetchone():
                    return error('ابتدا خروج این عضو از باشگاه ثبت شود.', 409)
        except (sqlite3.Error, OSError):
            return error('برای تغییر موبایل، اتصال حضور و غیاب لازم است.', 503)
    money = {}
    for key in ['debt', 'payment']:
        if key in payload:
            try:
                value = int(payload[key])
                if not 0 <= value <= 10**12:
                    raise ValueError
                money[key] = value
            except (ValueError, TypeError):
                return error('مبلغ باید عدد غیرمنفی معتبر باشد.')
    plan = None
    if payload.get('planId'):
        plan = Plan.objects.filter(pk=payload['planId'], is_active=True).first() if str(payload['planId']).isdigit() else None
        if not plan:
            return error('پلن فعال انتخاب کنید.')
    try:
        with transaction.atomic():
            if gym:
                LegacyMember.objects.filter(pk=gym.pk).update(**values, **money, **({'plan': plan.name} if plan else {}))
            if user:
                User.objects.filter(pk=user.pk).update(**values)
                if plan:
                    MembershipApplication.objects.filter(user=user).update(plan=plan)
            audit(request, f'ویرایش عضو {source}:{member_id}')
    except IntegrityError:
        return error('شماره موبایل یا کد ملی تکراری است.', 409)
    return JsonResponse({'ok': True})


def attendance_connection():
    return sqlite3.connect(settings.FITTRACK_ATTENDANCE_PATH.resolve().as_uri() + '?mode=ro', uri=True, timeout=5)


@owner_only
@require_http_methods(['GET'])
def activity(request):
    period = request.GET.get('period', 'today')
    if period not in {'today', 'month'}:
        return error('بازه معتبر نیست.')
    today = timezone.localdate()
    # The UI explicitly labels this as the current Gregorian calendar month.
    start = today if period == 'today' else today.replace(day=1)
    end = today + timedelta(days=1)
    since = timezone.make_aware(datetime.combine(start, time.min))
    until = timezone.make_aware(datetime.combine(end, time.min))
    events = LoginEvent.objects.filter(occurred_at__gte=since, occurred_at__lt=until)
    logins = [dict(name=e.user.get_full_name() or e.user.mobile, mobile=e.user.mobile, at=e.occurred_at.isoformat())
              for e in events.select_related('user').order_by('-occurred_at')[:500]]
    attendance = []
    available = True
    count = inside = unique = 0
    try:
        with closing(attendance_connection()) as conn:
            conn.row_factory = sqlite3.Row
            bounds = (start.isoformat(), end.isoformat())
            count, unique = conn.execute('SELECT COUNT(*), COUNT(DISTINCT member_id) FROM attendance_sessions WHERE checked_in_at>=? AND checked_in_at<?', bounds).fetchone()
            inside = conn.execute('SELECT COUNT(*) FROM attendance_sessions WHERE checked_out_at IS NULL').fetchone()[0]
            attendance = [dict(r) for r in conn.execute('SELECT member_id,full_name,mobile,plan,checked_in_at,checked_out_at,locker_id FROM attendance_sessions WHERE checked_in_at>=? AND checked_in_at<? ORDER BY checked_in_at DESC LIMIT 500', bounds)]
    except (sqlite3.Error, OSError):
        available = False
    return JsonResponse(dict(ok=True, period=period, start=start.isoformat(), end=today.isoformat(), logins=logins,
                             loginCount=events.count(), loginUsers=events.values('user_id').distinct().count(), attendance=attendance,
                             attendanceAvailable=available, visitCount=count, visitors=unique, inside=inside,
                             audit=[dict(action=a.action, at=a.occurred_at.isoformat()) for a in OwnerAudit.objects.order_by('-occurred_at')[:30]]))


def write_plan_catalog(plan, old_name=None):
    path = settings.FITTRACK_PLANS_PATH
    catalog = json.loads(path.read_text(encoding='utf-8-sig'))
    if not isinstance(catalog, dict):
        raise ValueError('Invalid plan catalog')
    for gender in ['مرد', 'زن', 'همه']:
        catalog[gender] = [p for p in catalog.get(gender, []) if p.get('name') not in {old_name, plan.name}]
    catalog[{'male': 'مرد', 'female': 'زن', 'all': 'همه'}[plan.gender]].append(dict(
        id=plan.id, name=plan.name, price=plan.price, sessions_per_month=plan.sessions_per_month, is_active=plan.is_active))
    # Replace atomically so the running desktop never sees half-written JSON.
    with tempfile.NamedTemporaryFile(mode='w', encoding='utf-8', dir=path.parent, delete=False, suffix='.json') as out:
        tmp = Path(out.name)
        json.dump(catalog, out, ensure_ascii=False, indent=2)
    try:
        tmp.replace(path)
    finally:
        tmp.unlink(missing_ok=True)


@owner_only
@require_http_methods(['GET', 'POST', 'PATCH'])
def plans(request, plan_id=None):
    if request.method == 'GET':
        return JsonResponse({'ok': True, 'plans': [_desktop_plan_payload(p) for p in Plan.objects.all()]})
    if (request.method == 'PATCH') != (plan_id is not None):
        return error('درخواست معتبر نیست.')
    current = Plan.objects.filter(pk=plan_id).first() if plan_id else None
    if plan_id and not current:
        return error('پلن پیدا نشد.', 404)
    payload = body_json(request) or {}
    if 'isActive' in payload and not isinstance(payload['isActive'], bool):
        return error('وضعیت پلن معتبر نیست.')
    values, invalid = _desktop_plan_values(payload, current)
    if invalid:
        return invalid
    if values['price'] > 10**12:
        return error('مبلغ بیش از حد مجاز است.')
    matches = re.findall(r'(\d+)\s*جلسه', values['name'].translate(str.maketrans('۰۱۲۳۴۵۶۷۸۹', '0123456789')))
    if not matches or int(matches[-1]) != values['sessions_per_month']:
        return error('نام پلن باید تعداد جلسات را داشته باشد؛ مثال: بدنسازی ۱۲ جلسه در ماه')
    old_name = current.name if current else None
    try:
        with transaction.atomic():
            if current:
                for key, value in values.items():
                    setattr(current, key, value)
                current.save()
                plan = current
            else:
                plan = Plan.objects.create(**values)
            # Existing members keep their purchased session entitlement/name.
            audit(request, f'ذخیره پلن {plan.id}: {plan.name}')
            write_plan_catalog(plan, old_name)
    except IntegrityError:
        return error('نام پلن تکراری است.', 409)
    except (OSError, ValueError, TypeError):
        return error('ذخیره کاتالوگ باشگاه انجام نشد؛ مسیر و دسترسی فایل پلن‌ها را بررسی کنید.', 503)
    return JsonResponse({'ok': True, 'plan': _desktop_plan_payload(plan)})
