import json
from tempfile import TemporaryDirectory

from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase, override_settings

from .models import DesktopDevice, DesktopLogEvent, DesktopRelease


@override_settings(
    FITTRACK_SYNC_SOURCE='test-gym',
    FITTRACK_DESKTOP_API_TOKEN='s' * 40,
)
class DesktopTelemetryTests(TestCase):
    def setUp(self):
        self.media = TemporaryDirectory()
        self.addCleanup(self.media.cleanup)
        self.override = override_settings(MEDIA_ROOT=self.media.name)
        self.override.enable()
        self.addCleanup(self.override.disable)

    def post(self, body, token='s' * 40):
        return self.client.post(
            '/api/desktop/telemetry',
            data=json.dumps(body),
            content_type='application/json',
            HTTP_AUTHORIZATION='Bearer ' + token,
        )

    def payload(self):
        return {
            'source': 'test-gym',
            'device': {
                'appVersion': '1.1.0',
                'platform': 'Windows 11',
                'stateSize': 1234,
                'freeDisk': 9999,
                'databaseOk': True,
                'pendingSync': 1,
                'processId': 42,
            },
            'logs': [{
                'id': 7,
                'level': 'ERROR',
                'logger': 'app.test',
                'message': 'failure detail',
                'occurredAt': '2026-11-17T10:00:00+03:30',
            }],
        }

    def test_heartbeat_and_logs_are_idempotent(self):
        for _ in range(2):
            response = self.post(self.payload())
            self.assertEqual(response.status_code, 200, response.content)
        device = DesktopDevice.objects.get(pk='test-gym')
        self.assertEqual(device.app_version, '1.1.0')
        self.assertTrue(device.database_ok)
        self.assertEqual(DesktopLogEvent.objects.count(), 1)

    def test_published_release_is_announced_and_download_requires_token(self):
        release = DesktopRelease.objects.create(
            version='1.2.0',
            notes='رفع خطای تمدید',
            package=SimpleUploadedFile('release.zip', b'zip-content'),
            sha256='a' * 64,
            signature='signed-manifest',
            package_size=11,
            is_published=True,
        )
        announced = self.post(self.payload()).json()['release']
        self.assertEqual(announced['version'], '1.2.0')
        self.assertIn(str(release.id), announced['downloadUrl'])
        path = f'/api/desktop/releases/{release.id}/download'
        self.assertEqual(self.client.get(path).status_code, 401)
        response = self.client.get(
            path, HTTP_AUTHORIZATION='Bearer ' + 's' * 40
        )
        self.assertEqual(response.status_code, 200)
        b''.join(response.streaming_content)
        response.close()

    def test_invalid_or_oversized_log_is_rejected(self):
        payload = self.payload()
        payload['logs'][0]['level'] = 'DEBUG'
        self.assertEqual(self.post(payload).status_code, 400)
        self.assertFalse(DesktopDevice.objects.exists())
