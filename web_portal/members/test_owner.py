import json
import sqlite3
import tempfile
from contextlib import closing
from datetime import timedelta
from pathlib import Path
from unittest.mock import patch

from django.core.cache import cache
from django.db import connection
from django.test import Client, TestCase
from django.utils import timezone
from .models import LegacyMember, LoginEvent, MembershipApplication, OwnerAudit, Plan, User


class OwnerTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        with connection.cursor() as c:
            c.execute('''CREATE TABLE IF NOT EXISTS users (
                id INTEGER PRIMARY KEY, first_name TEXT, last_name TEXT, father_name TEXT,
                national_id TEXT, certificate_no TEXT, address TEXT, mobile TEXT,
                age INTEGER, gender TEXT, plan TEXT, embedding TEXT, face_image BLOB,
                used_sessions INTEGER DEFAULT 0, signup_time TEXT, debt INTEGER DEFAULT 0, payment INTEGER DEFAULT 0)''')
        cls.owner = User.objects.create_superuser('09120000001', 'OwnerTest482!')
        cls.member = User.objects.create_user('09120000002', 'MemberTest482!', status='active', first_name='Member', last_name='One')
        cls.plan = Plan.objects.create(name='بدنسازی ۱۲ جلسه در ماه', price=100, sessions_per_month=12)
        cls.gym = LegacyMember.objects.create(first_name='Member',last_name='One',mobile=cls.member.mobile,gender='مرد',plan=cls.plan.name,signup_time='1405-06-01',embedding='SECRET',face_image=b'PRIVATE')
        MembershipApplication.objects.create(user=cls.member,plan=cls.plan,legacy_member_id=cls.gym.id,status='active')

    def setUp(self):
        cache.clear()
        self.client.force_login(self.owner)
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.catalog = Path(self.tmp.name)/'plans.json'
        self.catalog.write_text(json.dumps({'مرد':[{'name':self.plan.name,'price':100}], 'زن':[], 'همه':[]}),encoding='utf-8')
        self.attendance = Path(self.tmp.name)/'attendance.db'
        with closing(sqlite3.connect(self.attendance)) as c:
            c.execute('CREATE TABLE attendance_sessions(member_id INTEGER,full_name TEXT,mobile TEXT,plan TEXT,checked_in_at TEXT,checked_out_at TEXT,locker_id INTEGER)')
            c.execute('INSERT INTO attendance_sessions VALUES(?,?,?,?,?,?,?)',(self.gym.id,'Member',self.member.mobile,self.plan.name,timezone.localdate().isoformat()+' 10:00:00',None,1))
            c.commit()
        self.override = self.settings(FITTRACK_PLANS_PATH=self.catalog,FITTRACK_ATTENDANCE_PATH=self.attendance)
        self.override.enable(); self.addCleanup(self.override.disable)

    def test_owner_access_only_and_csrf(self):
        for user in [None,self.member]:
            c=Client()
            if user: c.force_login(user)
            for path in ['/api/owner/members','/api/owner/activity','/api/owner/plans']:
                self.assertEqual(c.get(path).status_code,403)
        c=Client(enforce_csrf_checks=True); c.force_login(self.owner)
        self.assertEqual(c.post('/api/owner/plans',data='{}',content_type='application/json').status_code,403)
        self.owner.status='suspended'; self.owner.save()
        self.assertEqual(self.client.get('/api/owner/members').status_code,403)

    def test_directory_includes_unlinked_gym_members_without_biometrics(self):
        LegacyMember.objects.create(first_name='Offline',last_name='Member',mobile='09120000003',gender='زن',plan=self.plan.name,signup_time='1405-06-01')
        response=self.client.get('/api/owner/members')
        self.assertEqual(len(response.json()['members']),3)
        self.assertNotIn(b'SECRET',response.content); self.assertNotIn(b'PRIVATE',response.content)

    def test_edit_updates_both_records_and_audits(self):
        r=self.client.patch(f'/api/owner/members/web/{self.member.id}',data=json.dumps({'firstName':'Updated','debt':123}),content_type='application/json')
        self.assertEqual(r.status_code,200)
        self.member.refresh_from_db(); self.gym.refresh_from_db()
        self.assertEqual(self.member.first_name,'Updated'); self.assertEqual(self.gym.first_name,'Updated'); self.assertEqual(self.gym.debt,123)
        self.assertEqual(OwnerAudit.objects.count(),1)

    def test_rejects_mobile_change_while_inside_and_duplicate_identity(self):
        endpoint=f'/api/owner/members/web/{self.member.id}'
        self.assertEqual(self.client.patch(endpoint,data=json.dumps({'mobile':'09120000004'}),content_type='application/json').status_code,409)
        self.assertEqual(self.client.patch(endpoint,data=json.dumps({'mobile':self.owner.mobile}),content_type='application/json').status_code,409)

    def test_plan_update_writes_desktop_catalog_and_preserves_purchase(self):
        r=self.client.patch(f'/api/owner/plans/{self.plan.id}',data=json.dumps({'name':'جدید ۱۶ جلسه در ماه','price':250,'sessionsPerMonth':16,'isActive':False}),content_type='application/json')
        self.assertEqual(r.status_code,200,r.content)
        data=json.loads(self.catalog.read_text(encoding='utf-8'))
        self.assertEqual(data['همه'][0]['price'],250)
        self.assertFalse(data['همه'][0]['is_active'])
        self.gym.refresh_from_db(); self.assertEqual(self.gym.plan,'بدنسازی ۱۲ جلسه در ماه')
        self.assertEqual(self.client.get('/api/plans').json()['plans'],[])

    def test_plan_file_failure_rolls_back_database(self):
        with patch('members.owner.write_plan_catalog',side_effect=OSError):
            r=self.client.patch(f'/api/owner/plans/{self.plan.id}',data=json.dumps({'price':900}),content_type='application/json')
        self.assertEqual(r.status_code,503); self.plan.refresh_from_db(); self.assertEqual(self.plan.price,100)
        self.assertEqual(OwnerAudit.objects.count(),0)

    def test_bad_plan_sessions_rejected(self):
        self.assertEqual(self.client.patch(f'/api/owner/plans/{self.plan.id}',data=json.dumps({'sessionsPerMonth':16}),content_type='application/json').status_code,400)

    def test_activity_counts_unique_users_and_attendance(self):
        LoginEvent.objects.create(user=self.member); LoginEvent.objects.create(user=self.member)
        LoginEvent.objects.create(user=self.member,occurred_at=timezone.now()-timedelta(days=40))
        data=self.client.get('/api/owner/activity?period=today').json()
        self.assertEqual(data['loginCount'],2); self.assertEqual(data['loginUsers'],1)
        self.assertEqual(data['visitCount'],1); self.assertEqual(data['inside'],1)
        self.assertEqual(self.client.get('/api/owner/activity?period=month').json()['loginCount'],2)

    def test_attendance_unavailable_is_explicit(self):
        with self.settings(FITTRACK_ATTENDANCE_PATH=Path(self.tmp.name)/'missing.db'):
            self.assertFalse(self.client.get('/api/owner/activity').json()['attendanceAvailable'])

    def test_successful_login_is_recorded_failed_login_is_not(self):
        c=Client()
        self.assertEqual(c.post('/api/login',data=json.dumps({'mobile':self.member.mobile,'password':'MemberTest482!'}),content_type='application/json').status_code,200)
        self.assertEqual(LoginEvent.objects.count(),1)
        c.post('/api/login',data=json.dumps({'mobile':self.member.mobile,'password':'wrong'}),content_type='application/json')
        self.assertEqual(LoginEvent.objects.count(),1)
