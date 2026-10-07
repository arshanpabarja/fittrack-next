import sqlite3
import tempfile
from contextlib import closing
from datetime import date
from pathlib import Path
from unittest.mock import patch

from django.test import Client, TestCase

from .models import GymSyncCursor, GymSyncRecord, LoginEvent, User


class AttendanceReportCases:
    remote = False

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.path = Path(self.tmp.name) / 'synthetic-attendance.db'
        with closing(sqlite3.connect(self.path)) as conn:
            conn.execute('CREATE TABLE attendance_sessions(member_id INTEGER,full_name TEXT,mobile TEXT,plan TEXT,checked_in_at TEXT,checked_out_at TEXT,locker_id INTEGER)')
        override = self.settings(FITTRACK_REMOTE_SYNC=self.remote, FITTRACK_ATTENDANCE_PATH=self.path)
        override.enable()
        self.addCleanup(override.disable)
        clock = patch('members.owner.timezone.localdate', return_value=date(2026, 10, 7))
        clock.start()
        self.addCleanup(clock.stop)
        self.manager = User.objects.create_user('09120000001', 'TestOnly482!', role='admin', status='active')
        self.client.force_login(self.manager)
        if self.remote:
            GymSyncCursor.objects.create(source='synthetic-only', sequence=1)
        self.next_id = 1

    def add_visit(self, member_id, at, name='مهدی ابهت', mobile='09120000002'):
        data = dict(member_id=member_id, full_name=name, mobile=mobile, plan='Gym 12',
                    checked_in_at=at, checked_out_at=at, locker_id=1)
        if self.remote:
            GymSyncRecord.objects.create(kind='attendance', local_id=self.next_id, data=data)
        else:
            with closing(sqlite3.connect(self.path)) as conn:
                conn.execute('INSERT INTO attendance_sessions VALUES(?,?,?,?,?,?,?)', tuple(data.values()))
                conn.commit()
        self.next_id += 1

    def test_history_uses_selected_period_and_keeps_duplicate_profiles_separate(self):
        for at in ['2026-09-30 23:59:59', '2026-10-01 00:00:00', '2026-10-07 23:59:59', '2026-10-08 00:00:00']:
            self.add_visit(7, at)
        self.add_visit(8, '2026-10-07 10:00:00')  # Same name and phone, different profile.
        for prefix in ('admin', 'owner'):
            response = self.client.get(f'/api/{prefix}/attendance/7')
            self.assertEqual(response.status_code, 200)
            self.assertEqual(response['Cache-Control'], 'no-store')
            data = response.json()
            self.assertEqual(data['start'], '2026-10-01')
            self.assertEqual(data['end'], '2026-10-07')
            self.assertEqual(data['visitCount'], 2)
            self.assertEqual([row['member_id'] for row in data['attendance']], [7, 7])
            self.assertEqual(data['attendance'][0]['checked_in_at'], '2026-10-07 23:59:59')
            today = self.client.get(f'/api/{prefix}/attendance/7?period=today').json()
            self.assertEqual(today['start'], '2026-10-07')
            self.assertEqual(today['visitCount'], 1)
            self.assertEqual(today['period'], 'today')
            # Switching the dialog period does not alter subsequent report requests.
            self.assertEqual(self.client.get(f'/api/{prefix}/activity?period=month').json()['visitCount'], 3)

    def test_name_phone_and_persian_digits_search_before_display_limit(self):
        self.add_visit(7, '2026-10-07 06:00:00')
        for i in range(501):
            self.add_visit(8, '2026-10-07 12:00:00', 'عضو دیگر', '09120000003')
        self.assertEqual(len(self.client.get('/api/admin/activity').json()['attendance']), 500)
        for search in ['مهدی ابهت', 'ابهت', '۰۹۱۲۰۰۰۰۰۰۲', '٠٩١٢٠٠٠٠٠٠٢', '000002']:
            with self.subTest(search=search):
                data = self.client.get('/api/admin/activity', {'search': search}).json()
                self.assertEqual(data['visitCount'], 1)
                self.assertEqual(data['visitors'], 1)
                self.assertEqual(data['attendance'][0]['member_id'], 7)

    def test_history_pagination_preserves_total_and_deterministic_rows(self):
        for i in range(53):
            self.add_visit(7, '2026-10-07 10:00:00', name=f'Visit {i}')
        first = self.client.get('/api/admin/attendance/7').json()
        second = self.client.get('/api/admin/attendance/7?page=2').json()
        self.assertEqual(first['visitCount'], 53)
        self.assertEqual(len(first['attendance']), 50)
        self.assertTrue(first['hasNext'])
        self.assertEqual(second['visitCount'], 53)
        self.assertEqual(len(second['attendance']), 3)
        self.assertFalse(second['hasNext'])
        self.assertEqual(len({a['full_name'] for a in first['attendance'] + second['attendance']}), 53)

    def test_activity_search_respects_today_and_month_and_empty_history(self):
        self.add_visit(7, '2026-10-01 10:00:00')
        self.add_visit(7, '2026-10-07 10:00:00')
        self.add_visit(7, '2026-09-30 10:00:00')
        for search in ('ابهت', '۰۹۱۲۰۰۰۰۰۰۲'):
            self.assertEqual(self.client.get('/api/admin/activity', {'period': 'today', 'search': search}).json()['visitCount'], 1)
            self.assertEqual(self.client.get('/api/admin/activity', {'period': 'month', 'search': search}).json()['visitCount'], 2)
        data = self.client.get('/api/admin/attendance/999').json()
        self.assertTrue(data['attendanceAvailable'])
        self.assertEqual(data['visitCount'], 0)
        self.assertEqual(data['attendance'], [])

    def test_login_search_matches_first_last_names_and_phone(self):
        member = User.objects.create_user('09120000002', first_name='مهدی', last_name='ابهت')
        LoginEvent.objects.create(user=member, occurred_at='2026-10-07T10:00:00+03:30')
        LoginEvent.objects.create(user=self.manager, occurred_at='2026-10-07T10:00:00+03:30')
        for search in ('مهدی ابهت', 'ابهت', '۰۹۱۲۰۰۰۰۰۰۲'):
            data = self.client.get('/api/admin/activity', {'search': search}).json()
            self.assertEqual(data['loginCount'], 1)
            self.assertEqual(data['loginUsers'], 1)
            self.assertEqual(data['logins'][0]['mobile'], member.mobile)

    def test_history_rejects_unauthorized_users_and_bad_pages(self):
        anonymous = Client()
        self.assertEqual(anonymous.get('/api/admin/attendance/7').status_code, 403)
        member = User.objects.create_user('09120000002', status='active')
        anonymous.force_login(member)
        self.assertEqual(anonymous.get('/api/owner/attendance/7').status_code, 403)
        for page in ('0', '-1', 'abc', '1000001'):
            self.assertEqual(self.client.get('/api/admin/attendance/7', {'page': page}).status_code, 400)
        self.assertEqual(self.client.get('/api/admin/attendance/7?period=invalid').status_code, 400)
        self.manager.status = 'suspended'
        self.manager.save()
        self.assertEqual(self.client.get('/api/admin/attendance/7').status_code, 403)


class LocalAttendanceReports(AttendanceReportCases, TestCase):
    def test_missing_source_is_not_reported_as_zero_visits(self):
        with self.settings(FITTRACK_ATTENDANCE_PATH=Path(self.tmp.name) / 'missing.db'):
            self.assertFalse(self.client.get('/api/admin/attendance/7').json()['attendanceAvailable'])

    def test_search_treats_sql_wildcards_as_literal_text(self):
        self.add_visit(7, '2026-10-07 10:00:00')
        for search in ('%', '_', "' OR 1=1 --"):
            self.assertEqual(self.client.get('/api/admin/activity', {'search': search}).json()['visitCount'], 0)


class RemoteAttendanceReports(AttendanceReportCases, TestCase):
    remote = True

    def test_remote_reports_never_read_local_database(self):
        self.add_visit(7, '2026-10-07 10:00:00')
        with patch('members.attendance_reports.sqlite3.connect', side_effect=AssertionError('local database must not be read')):
            self.assertEqual(self.client.get('/api/admin/attendance/7').json()['visitCount'], 1)
            self.assertEqual(self.client.get('/api/admin/activity').json()['visitCount'], 1)

    def test_no_sync_is_distinct_from_empty_attendance(self):
        GymSyncCursor.objects.all().delete()
        data = self.client.get('/api/admin/attendance/7').json()
        self.assertFalse(data['attendanceAvailable'])
        self.assertIsNone(data['syncedAt'])
