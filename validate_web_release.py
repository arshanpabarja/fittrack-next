"""Smoke-test the actual web ZIP in isolation with production settings and fake data."""
import hashlib
import json
import os
from pathlib import Path
import secrets
import subprocess
import sys
from tempfile import TemporaryDirectory
from zipfile import ZipFile

from build_web_release import ROOT, build_release


SMOKE = r'''
import json
import django
django.setup()
from django.conf import settings
from django.test import Client
from django.core.checks import run_checks
from members.models import User
from app.domain.dates import membership_expires_at
assert membership_expires_at('1405-07-01').startswith('1405-08-01')
assert settings.DEBUG is False
assert settings.SESSION_COOKIE_SECURE and settings.CSRF_COOKIE_SECURE
assert settings.SECURE_SSL_REDIRECT and settings.SECURE_HSTS_SECONDS > 0
assert not (settings.STATIC_ROOT / 'admin.html').exists()
assert not (settings.STATIC_ROOT / 'server.py').exists()
# These two optional policies affect every subdomain/browser preload registration.
# Keep them disabled until domain-wide HTTPS is confirmed; reject all other issues.
issues = run_checks(include_deployment_checks=True)
assert all(issue.id in {'security.W005', 'security.W021'} for issue in issues), issues
host = {'HTTP_HOST': 'lifeboxgym.com'}
anonymous = Client(enforce_csrf_checks=True)
assert anonymous.get('/admin', **host).status_code == 301
assert anonymous.get('/admin', HTTP_X_FORWARDED_PROTO='https', **host).status_code == 302
assert anonymous.get('/api/owner/overview', secure=True, **host).status_code == 403
login_page = anonymous.get('/login', secure=True, **host)
assert login_page.status_code == 200
assert login_page.cookies['csrftoken']['secure']
for path in ('/owner.js', '/owner.css', '/coach.js', '/coach.css', '/assets/icons/users.svg', '/assets/Vazirmatn-Variable.ttf'):
    response = anonymous.get(path, secure=True, **host)
    assert response.status_code == 200, path
    response.close()
User.objects.create_superuser(mobile='09120000001', password='ReleaseTestOnly482!')
payload = json.dumps({'mobile': '09120000001', 'password': 'ReleaseTestOnly482!'})
assert anonymous.post('/api/login', data=payload, content_type='application/json', secure=True, **host).status_code == 403
csrf = anonymous.cookies['csrftoken'].value
response = anonymous.post('/api/login', data=payload, content_type='application/json',
    secure=True, HTTP_X_CSRFTOKEN=csrf, HTTP_ORIGIN='https://lifeboxgym.com', **host)
assert response.status_code == 200, response.status_code
assert response.cookies['sessionid']['secure']
assert response.cookies['sessionid']['httponly']
panel = anonymous.get('/owner', secure=True, **host)
assert panel.status_code == 200
assert panel['Cache-Control'] == 'no-store'
assert panel['X-Frame-Options'] == 'DENY'
assert 'max-age=' in panel['Strict-Transport-Security']
for path in ('/api/owner/members', '/api/owner/plans', '/api/owner/activity', '/api/owner/overview'):
    response = anonymous.get(path, secure=True, **host)
    assert response.status_code == 200, (path, response.content)
    assert response['Cache-Control'] == 'no-store'
    assert response.json()['ok'] is True
assert anonymous.get('/admin', secure=True, HTTP_HOST='untrusted.example').status_code == 400
limited = User.objects.create_user(mobile='09120000002', password='LimitedTestOnly482!', role='admin', status='active')
anonymous.force_login(limited)
assert anonymous.get('/admin', secure=True, **host).status_code == 200
assert anonymous.get('/owner', secure=True, **host).status_code == 302
insights = anonymous.get('/api/owner/overview', secure=True, **host).json()
assert 'monthPayments' not in insights['metrics']
assert all('payments' not in point for point in insights['series'])
coach = User.objects.create_user(mobile='09120000003', password='CoachReleaseOnly482!', role='coach', status='active')
anonymous.force_login(coach)
assert anonymous.get('/coach-panel', secure=True, **host).status_code == 200
workspace = anonymous.get('/api/coach/workspace', secure=True, **host)
assert workspace.status_code == 200 and workspace.json()['clients'] == []
assert 'no-store' in workspace['Cache-Control']
assert len(anonymous.get('/api/coach/exercises', secure=True, **host).json()['exercises']) == 10
assert anonymous.get('/api/owner/overview', secure=True, **host).status_code == 403
member = User.objects.create_user(mobile='09120000004', password='MemberReleaseOnly482!', role='member', status='active')
anonymous.force_login(member)
panel = anonymous.get('/dashboard', secure=True, **host)
assert panel.status_code == 200 and b'member-bootstrap' in panel.content
assert 'no-store' in panel['Cache-Control']
workspace = anonymous.get('/api/member/workspace', secure=True, **host)
assert workspace.status_code == 200 and workspace.json()['program'] is None
assert workspace.json()['workouts'] == []
assert 'no-store' in workspace['Cache-Control']
for path in ('/member.css', '/member.js', '/assets/Vazirmatn-Variable.woff2'):
    assert anonymous.get(path, secure=True, **host).status_code == 200
assert anonymous.get('/api/owner/overview', secure=True, **host).status_code == 403
print('Production smoke passed: HTTPS, proxy, cookies, CSRF, owner/admin separation, APIs, assets, shared calendar')
'''


def main():
    output, count = build_release(ROOT / 'dist/lifebox-web.zip')
    with TemporaryDirectory(prefix='lifebox-release-') as temporary:
        directory = Path(temporary)
        release = directory / 'release'
        with ZipFile(output) as archive:
            names = archive.namelist()
            assert not any(name.startswith(('state/', 'database/', 'lifebox-landing/data/', '.venv/')) for name in names)
            assert not any(Path(name).suffix in {'.db', '.sqlite', '.sqlite3'} or Path(name).name == '.env' for name in names)
            manifest = json.loads(archive.read('release-manifest.json'))
            assert set(manifest) == set(names) - {'release-manifest.json'}
            for name, digest in manifest.items():
                assert hashlib.sha256(archive.read(name)).hexdigest() == digest, name
            archive.extractall(release)

        env = {key: value for key, value in os.environ.items()
               if not key.startswith(('DJANGO_', 'FITTRACK_', 'SMS_IR_')) and key != 'PYTHONPATH'}
        env.update({
            'DJANGO_SETTINGS_MODULE': 'config.settings', 'DJANGO_DEBUG': '0',
            'DJANGO_SECRET_KEY': secrets.token_urlsafe(64),
            'DJANGO_ALLOWED_HOSTS': 'lifeboxgym.com',
            'DJANGO_CSRF_TRUSTED_ORIGINS': 'https://lifeboxgym.com',
            'DJANGO_TRUST_PROXY_SSL': '1',
            'FITTRACK_DB_PATH': str(directory / 'fake-members.db'),
            'FITTRACK_REMOTE_SYNC': '1', 'FITTRACK_SYNC_SOURCE': 'release-test-only',
            'FITTRACK_DESKTOP_API_TOKEN': secrets.token_urlsafe(48),
            'SMS_IR_API_KEY': 'fake-release-test-no-network',
        })
        cwd = release / 'web_portal'
        for arguments in (
            ['manage.py', 'check', '--deploy', '--fail-level', 'ERROR'],
            ['manage.py', 'migrate', '--noinput'],
            ['manage.py', 'collectstatic', '--noinput'],
            ['-c', SMOKE],
        ):
            result = subprocess.run([sys.executable, *arguments], cwd=cwd, env=env,
                                    capture_output=True, text=True, encoding='utf-8', errors='replace')
            if result.returncode:
                print(result.stdout)
                print(result.stderr)
                raise SystemExit(result.returncode)
            lines = result.stdout.strip().splitlines()
            print(lines[-1] if lines else 'Deployment check completed (optional domain-wide HSTS policies deferred)')
        invalid = {**env, 'DJANGO_SECRET_KEY': ''}
        rejected = subprocess.run([sys.executable, 'manage.py', 'check'], cwd=cwd, env=invalid,
                                  capture_output=True, text=True, encoding='utf-8', errors='replace')
        assert rejected.returncode != 0 and 'DJANGO_SECRET_KEY' in rejected.stderr
        assert env['SMS_IR_API_KEY'] not in rejected.stderr
        print('Production startup correctly refuses a missing secret without revealing credentials')
    print(f'Validated package: {output} ({count} files)')


if __name__ == '__main__':
    main()
