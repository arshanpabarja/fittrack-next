import json
import secrets

from django.conf import settings
from django.db import transaction
from django.http import FileResponse, JsonResponse
from django.shortcuts import get_object_or_404
from django.utils.dateparse import parse_datetime
from django.utils import timezone
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_GET, require_POST

from .models import (
    DesktopDevice,
    DesktopLogEvent,
    DesktopRelease,
    DesktopUpdateAttempt,
)
from app.core.update_security import version_tuple


def _error(message, status=400):
    return JsonResponse({'ok': False, 'message': message}, status=status)


def _authorized(request):
    from .views import _desktop_authorized

    return _desktop_authorized(request)


def _release_payload(request, current_version):
    try:
        current_key = version_tuple(current_version)
    except ValueError:
        current_key = (0, 0, 0)
    releases = []
    for candidate in DesktopRelease.objects.filter(is_published=True):
        try:
            if version_tuple(candidate.version) > current_key:
                releases.append(candidate)
        except ValueError:
            continue
    release = max(releases, key=lambda item: version_tuple(item.version), default=None)
    if not release:
        return None
    return {
        'id': release.id,
        'version': release.version,
        'notes': release.notes,
        'size': release.package_size,
        'sha256': release.sha256,
        'signature': release.signature,
        'downloadUrl': request.build_absolute_uri(
            f'/api/desktop/releases/{release.id}/download'
        ),
    }


@csrf_exempt
@require_POST
def telemetry_api(request):
    if not _authorized(request):
        return _error('توکن معتبر نیست.', status=401)
    if len(request.body) > 256 * 1024:
        return _error('حجم گزارش بیش از حد مجاز است.', status=413)
    try:
        body = json.loads(request.body)
        source = body['source']
        device_data = body['device']
        logs = body.get('logs', [])
        update_status = body.get('updateStatus')
        expected_device = {
            'appVersion', 'platform', 'stateSize', 'freeDisk',
            'databaseOk', 'pendingSync', 'processId',
        }
        if (
            not isinstance(source, str)
            or len(source) > 80
            or not settings.FITTRACK_SYNC_SOURCE
            or not secrets.compare_digest(
                source.encode(), settings.FITTRACK_SYNC_SOURCE.encode()
            )
            or not isinstance(device_data, dict)
            or set(device_data) != expected_device
            or not isinstance(logs, list)
            or len(logs) > 100
        ):
            raise ValueError('ساختار گزارش دستگاه معتبر نیست.')
        if not isinstance(device_data['appVersion'], str) or len(device_data['appVersion']) > 40:
            raise ValueError('نسخه برنامه معتبر نیست.')
        if not isinstance(device_data['platform'], str) or len(device_data['platform']) > 120:
            raise ValueError('مشخصات سیستم معتبر نیست.')
        for key in ('stateSize', 'freeDisk', 'pendingSync', 'processId'):
            if type(device_data[key]) is not int or not 0 <= device_data[key] < 2**63:
                raise ValueError('مقدار وضعیت دستگاه معتبر نیست.')
        if type(device_data['databaseOk']) is not bool:
            raise ValueError('وضعیت دیتابیس معتبر نیست.')
        normalized_logs = []
        for item in logs:
            if not isinstance(item, dict) or set(item) != {
                'id', 'level', 'logger', 'message', 'occurredAt'
            }:
                raise ValueError('ساختار لاگ معتبر نیست.')
            occurred_at = parse_datetime(item['occurredAt'])
            if (
                type(item['id']) is not int
                or not 0 < item['id'] < 2**63
                or item['level'] not in {'WARNING', 'ERROR', 'CRITICAL'}
                or not isinstance(item['logger'], str)
                or len(item['logger']) > 200
                or not isinstance(item['message'], str)
                or len(item['message']) > 12000
                or occurred_at is None
            ):
                raise ValueError('محتوای لاگ معتبر نیست.')
            if timezone.is_naive(occurred_at):
                occurred_at = timezone.make_aware(occurred_at)
            normalized_logs.append((item, occurred_at))
        if update_status is not None:
            if not isinstance(update_status, dict) or set(update_status) != {
                'version', 'status', 'error'
            }:
                raise ValueError('وضعیت آپدیت معتبر نیست.')
            if update_status['status'] not in DesktopUpdateAttempt.Status.values:
                raise ValueError('مرحله آپدیت معتبر نیست.')
            if (
                not isinstance(update_status['version'], str)
                or len(update_status['version']) > 40
                or not isinstance(update_status['error'], str)
                or len(update_status['error']) > 1000
            ):
                raise ValueError('جزئیات آپدیت معتبر نیست.')
    except (KeyError, TypeError, ValueError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        return _error(str(exc) or 'گزارش دستگاه معتبر نیست.')

    with transaction.atomic():
        device, _ = DesktopDevice.objects.update_or_create(
            source=source,
            defaults={
                'app_version': device_data['appVersion'],
                'platform': device_data['platform'],
                'state_size': device_data['stateSize'],
                'free_disk': device_data['freeDisk'],
                'database_ok': device_data['databaseOk'],
                'pending_sync': device_data['pendingSync'],
                'process_id': device_data['processId'],
            },
        )
        for item, occurred_at in normalized_logs:
            DesktopLogEvent.objects.update_or_create(
                device=device,
                local_id=item['id'],
                defaults={
                    'level': item['level'],
                    'logger': item['logger'],
                    'message': item['message'],
                    'occurred_at': occurred_at,
                },
            )
        if update_status is not None:
            release = DesktopRelease.objects.filter(
                version=update_status['version']
            ).first()
            if release:
                DesktopUpdateAttempt.objects.create(
                    device=device,
                    release=release,
                    status=update_status['status'],
                    error=str(update_status['error'])[:1000],
                )
    return JsonResponse({
        'ok': True,
        'release': _release_payload(request, device_data['appVersion']),
    })


@require_GET
def download_release(request, release_id):
    if not _authorized(request):
        return _error('توکن معتبر نیست.', status=401)
    release = get_object_or_404(
        DesktopRelease, pk=release_id, is_published=True
    )
    return FileResponse(
        release.package.open('rb'),
        as_attachment=True,
        filename=f'LifeBox-{release.version}.zip',
        content_type='application/zip',
    )
