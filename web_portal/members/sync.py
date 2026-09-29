"""Authenticated, ordered single-gym replication. No biometric payload is accepted."""
import hashlib
import json
import logging
import secrets

from django.conf import settings
from django.db import IntegrityError, transaction
from django.http import JsonResponse
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_POST

from .models import GymSyncCursor, GymSyncRecord, LegacyMember, Plan


FIELDS = {
    'member': set('first_name last_name father_name national_id certificate_no address mobile age gender plan used_sessions signup_time debt payment face_registered'.split()),
    'plan': set('name price gender sessions_per_month is_active'.split()),
    'attendance': set('member_id full_name mobile plan checked_in_at checked_out_at locker_id'.split()),
    'renewal': set('member_id previous_plan new_plan carried_sessions membership_started_at paid_amount payment_reference renewed_at'.split()),
}
NUMBERS = set('age used_sessions debt payment price sessions_per_month member_id locker_id carried_sessions paid_amount'.split())
BOOLEANS = {'face_registered', 'is_active'}
NULLABLE = set('father_name national_id certificate_no address age checked_out_at locker_id'.split())


def validate(record):
    if not isinstance(record, dict) or set(record) != {'kind', 'id', 'data'}:
        raise ValueError('ساختار رکورد معتبر نیست.')
    kind, key, data = record['kind'], record['id'], record['data']
    if kind not in FIELDS or type(key) is not int or not 0 < key < 2**53:
        raise ValueError('شناسه رکورد معتبر نیست.')
    if data is None:
        return
    if not isinstance(data, dict) or set(data) != FIELDS[kind]:
        raise ValueError('فیلدهای همگام‌سازی معتبر نیست.')
    for field, value in data.items():
        if value is None and field in NULLABLE:
            continue
        if field in BOOLEANS:
            valid = type(value) is bool
        elif field in NUMBERS:
            valid = type(value) is int and abs(value) <= 10**12
        else:
            valid = isinstance(value, str) and len(value) <= 10000
        if not valid:
            raise ValueError('نوع یا طول فیلد معتبر نیست.')
    if kind == 'plan' and (data['gender'] not in {'all', 'male', 'female'} or
                           data['price'] < 0 or not 0 <= data['sessions_per_month'] <= 60 or
                           not data['name'] or len(data['name']) > 150):
        raise ValueError('پلن معتبر نیست.')


@csrf_exempt
@require_POST
def sync_api(request):
    from .views import _desktop_authorized, error
    if not settings.FITTRACK_REMOTE_SYNC:
        return error('همگام‌سازی راه دور فعال نیست.', status=409)
    if not _desktop_authorized(request):
        return error('توکن معتبر نیست.', status=401)
    if len(request.body) > 1024 * 1024:
        return error('حجم درخواست بیش از حد مجاز است.', status=413)
    try:
        body = json.loads(request.body)
        if not isinstance(body, dict):
            raise ValueError()
        source, sequence, records = body.get('source'), body.get('sequence'), body.get('records')
        if not isinstance(source, str) or len(source) > 80 or not settings.FITTRACK_SYNC_SOURCE or not secrets.compare_digest(source.encode(), settings.FITTRACK_SYNC_SOURCE.encode()):
            return error('شناسه دستگاه باشگاه مطابقت ندارد.', status=403)
        if type(sequence) is not int or not 0 < sequence < 2**53 or not isinstance(records, list) or not 0 <= len(records) <= 100:
            raise ValueError('شماره یا اندازه دسته معتبر نیست.')
        for record in records:
            validate(record)
        if len({(r['kind'], r['id']) for r in records}) != len(records):
            raise ValueError('رکورد تکراری در دسته وجود دارد.')
    except (ValueError, TypeError, UnicodeDecodeError) as exc:
        return error(str(exc) or 'درخواست معتبر نیست.')
    digest = hashlib.sha256(json.dumps(body, ensure_ascii=False, sort_keys=True).encode()).hexdigest()
    try:
        with transaction.atomic():
            cursor, _ = GymSyncCursor.objects.get_or_create(source=source)
            if cursor.sequence == sequence and cursor.digest == digest:
                return JsonResponse(dict(ok=True, sequence=sequence))
            # Compare-and-swap also prevents parallel requests from committing out of order.
            if sequence != cursor.sequence + 1 or not GymSyncCursor.objects.filter(source=source, sequence=sequence-1).update(sequence=sequence, digest=digest):
                return error('ترتیب همگام‌سازی ناسازگار است؛ فایل صف دستگاه را حذف نکنید.', status=409)
            for record in records:
                kind, key, data = record['kind'], record['id'], record['data']
                if data is None:
                    known = GymSyncRecord.objects.filter(kind=kind, local_id=key)
                    if known.exists():
                        if kind == 'member':
                            LegacyMember.objects.filter(pk=key).delete()
                        elif kind == 'plan':
                            # Keep purchased plan references and historical applications intact.
                            Plan.objects.filter(pk=key).update(is_active=False)
                        known.delete()
                    continue
                if kind == 'member':
                    values = {k: v for k, v in data.items() if k != 'face_registered'}
                    existing = LegacyMember.objects.filter(pk=key).exists()
                    known = GymSyncRecord.objects.filter(kind=kind, local_id=key).exists()
                    if existing and not known:
                        raise ValueError('سرور از قبل عضو دارد؛ انتقال اولیه نیاز به تطبیق شناسه‌ها دارد.')
                    LegacyMember.objects.update_or_create(pk=key, defaults=values)
                elif kind == 'plan':
                    existing = Plan.objects.filter(pk=key).first()
                    known = GymSyncRecord.objects.filter(kind=kind, local_id=key).exists()
                    if existing and not known and existing.name != data['name']:
                        raise ValueError('شناسه پلن سرور با باشگاه متفاوت است؛ ابتدا پلن‌ها تطبیق داده شوند.')
                    Plan.objects.update_or_create(pk=key, defaults=data)
                GymSyncRecord.objects.update_or_create(kind=kind, local_id=key, defaults={'data': data})
            cursor.refresh_from_db()
            cursor.save(update_fields=['updated_at'])
    except (IntegrityError, ValueError) as exc:
        if isinstance(exc, IntegrityError):
            logging.getLogger(__name__).warning(
                'Gym sync rejected: sequence=%s kind=%s id=%s constraint=%s',
                sequence, record['kind'] if records else '-',
                record['id'] if records else '-', str(exc),
            )
        return error(str(exc) if isinstance(exc, ValueError) else 'اطلاعات با رکورد موجود سرور تداخل دارد.', status=409)
    return JsonResponse(dict(ok=True, sequence=sequence))
