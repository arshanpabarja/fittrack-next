"""Production must refuse unsafe or incomplete service configuration."""
from pathlib import Path
import secrets
from tempfile import TemporaryDirectory

from django.core.exceptions import ImproperlyConfigured
from django.test import SimpleTestCase

from config.deployment import validate_production


class ProductionConfigurationTests(SimpleTestCase):
    def setUp(self):
        self.temporary = TemporaryDirectory(prefix='lifebox-config-test-')
        self.addCleanup(self.temporary.cleanup)
        self.env = {
            'DJANGO_SECRET_KEY': secrets.token_urlsafe(64),
            'DJANGO_ALLOWED_HOSTS': 'lifeboxgym.com',
            'DJANGO_CSRF_TRUSTED_ORIGINS': 'https://lifeboxgym.com',
            'FITTRACK_DB_PATH': str(Path(self.temporary.name) / 'fake.db'),
            'SMS_IR_API_KEY': 'fake-sms-only',
            'FITTRACK_DESKTOP_API_TOKEN': secrets.token_urlsafe(48),
            'FITTRACK_REMOTE_SYNC': '1', 'FITTRACK_SYNC_SOURCE': 'test-only',
        }

    def test_valid_configuration_is_accepted(self):
        validate_production(self.env)

    def test_required_settings_cannot_be_missing_or_placeholders(self):
        for key in ('DJANGO_SECRET_KEY', 'DJANGO_ALLOWED_HOSTS', 'DJANGO_CSRF_TRUSTED_ORIGINS',
                    'FITTRACK_DB_PATH', 'SMS_IR_API_KEY', 'FITTRACK_DESKTOP_API_TOKEN', 'FITTRACK_SYNC_SOURCE'):
            for value in ('', 'replace-with-private-value'):
                with self.subTest(key=key, value=value), self.assertRaises(ImproperlyConfigured):
                    validate_production({**self.env, key: value})

    def test_unsafe_values_are_rejected_without_revealing_secrets(self):
        for key, value in (
            ('DJANGO_SECRET_KEY', 'x' * 60),
            ('DJANGO_SECRET_KEY', 'django-insecure-' + secrets.token_urlsafe(64)),
            ('DJANGO_ALLOWED_HOSTS', '*'),
            ('DJANGO_ALLOWED_HOSTS', 'https://lifeboxgym.com'),
            ('DJANGO_CSRF_TRUSTED_ORIGINS', 'http://lifeboxgym.com'),
            ('DJANGO_CSRF_TRUSTED_ORIGINS', 'https://lifeboxgym.com/path'),
            ('DJANGO_CSRF_TRUSTED_ORIGINS', 'https://[invalid'),
            ('FITTRACK_DB_PATH', 'database/gym_users.db'),
            ('FITTRACK_DB_PATH', str(Path(__file__).resolve().parents[2] / 'fake.db')),
            ('FITTRACK_DESKTOP_API_TOKEN', 'dev-fittrack-desktop-token-change-before-public'),
        ):
            with self.subTest(key=key):
                with self.assertRaises(ImproperlyConfigured) as error:
                    validate_production({**self.env, key: value})
                self.assertNotIn(self.env['SMS_IR_API_KEY'], str(error.exception))
                self.assertNotIn(self.env['DJANGO_SECRET_KEY'], str(error.exception))

    def test_local_deployment_does_not_require_a_remote_sync_source(self):
        validate_production({**self.env, 'FITTRACK_REMOTE_SYNC': '0', 'FITTRACK_SYNC_SOURCE': ''})
