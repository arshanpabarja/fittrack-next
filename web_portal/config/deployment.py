"""Fail closed when production is missing deployment-specific configuration."""
import re
from pathlib import Path
from urllib.parse import urlsplit

from django.core.exceptions import ImproperlyConfigured


def validate_production(env):
    problems = []

    def require(name):
        value = env.get(name, '').strip()
        if not value or 'replace-' in value.lower() or 'change-before-public' in value.lower():
            problems.append(f'{name} must be configured in the service environment')
        return value

    secret = require('DJANGO_SECRET_KEY')
    if len(secret) < 50 or len(set(secret)) < 5 or secret.startswith('django-insecure-'):
        problems.append('DJANGO_SECRET_KEY must be a strong random secret of at least 50 characters')

    hosts = [value.strip() for value in require('DJANGO_ALLOWED_HOSTS').split(',') if value.strip()]
    if not hosts or any(not re.fullmatch(r'\.?[a-zA-Z0-9][a-zA-Z0-9.-]*|\[[0-9a-fA-F:]+\]', value) for value in hosts):
        problems.append('DJANGO_ALLOWED_HOSTS must contain bare hosts without schemes, ports or wildcards')

    origins = [value.strip() for value in require('DJANGO_CSRF_TRUSTED_ORIGINS').split(',') if value.strip()]
    for origin in origins:
        try:
            parsed = urlsplit(origin)
            parsed.port
        except ValueError:
            problems.append('DJANGO_CSRF_TRUSTED_ORIGINS must contain valid HTTPS origins')
            break
        if (parsed.scheme != 'https' or not parsed.hostname or parsed.username or parsed.password
                or parsed.path or parsed.query or parsed.fragment or '*' in origin):
            problems.append('DJANGO_CSRF_TRUSTED_ORIGINS must contain exact HTTPS origins')
            break

    database = require('FITTRACK_DB_PATH')
    if not Path(database).is_absolute():
        problems.append('FITTRACK_DB_PATH must be an explicit absolute path outside the release')
    elif Path(database).resolve().is_relative_to(Path(__file__).resolve().parents[2]):
        problems.append('FITTRACK_DB_PATH must be outside the release directory')

    require('SMS_IR_API_KEY')
    token = require('FITTRACK_DESKTOP_API_TOKEN')
    if len(token) < 32 or len(set(token)) < 5:
        problems.append('FITTRACK_DESKTOP_API_TOKEN must be a strong random token of at least 32 characters')
    if env.get('FITTRACK_REMOTE_SYNC', '0') == '1':
        require('FITTRACK_SYNC_SOURCE')

    if problems:
        # Only names and requirements are reported, never secret values.
        raise ImproperlyConfigured('Production configuration: ' + '; '.join(problems))
