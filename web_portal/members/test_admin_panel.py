import importlib
import json
from types import SimpleNamespace

from django.contrib import admin
from django.contrib.auth.models import Permission
from django.test import Client, TestCase, override_settings
from django.utils import timezone

from .models import GymRemoteCommand, GymSyncCursor, GymSyncRecord, LegacyMember, Plan, User


@override_settings(FITTRACK_REMOTE_SYNC=True, FITTRACK_SYNC_SOURCE='test-only')
class LimitedAdminTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.owner = User.objects.create_superuser('09129999991', 'OwnerTestOnly482!')
        # Deliberately grant Django model permission: role policy must still deny access.
        cls.admin = User.objects.create_user('09129999992', 'AdminTestOnly482!', role='admin', status='active', is_staff=True)
        cls.admin.user_permissions.add(*Permission.objects.all())
        cls.member = User.objects.create_user('09129999993', 'MemberTestOnly482!', status='active')
        cls.plan = Plan.objects.create(name='بدنسازی ۱۲ جلسه', price=1000, sessions_per_month=12)
        cls.gym = LegacyMember.objects.create(first_name='Test', last_name='Member', mobile=cls.member.mobile,
            plan=cls.plan.name, used_sessions=0, signup_time='1405-07-10', debt=90, payment=800,
            embedding='PRIVATE', face_image=b'PRIVATE')
        GymSyncCursor.objects.create(source='test-only', sequence=1)
        GymSyncRecord.objects.create(kind='renewal', local_id=1, data={
            'member_id': cls.gym.pk, 'new_plan': cls.plan.name, 'paid_amount': 123,
            'payment_reference': 'fake-only', 'renewed_at': timezone.now().isoformat()})

    def setUp(self):
        self.client.force_login(self.admin)

    def test_separate_pages_and_no_financial_or_plan_controls_in_admin_html(self):
        response = self.client.get('/admin')
        self.assertEqual(response.status_code, 200)
        content = response.content.decode()
        self.assertIn('پنل ادمین باشگاه', content)
        self.assertIn('data-panel-role="admin"', content)
        self.assertIn('name="debt"', content)
        for forbidden in ('revenue-chart', 'metric-revenue', 'chart-total', 'payment-today', 'payment-month',
                          'plan-form', 'name="planId"', 'name="payment"', '/django-admin/'):
            self.assertNotIn(forbidden, content)
        self.assertEqual(response['Cache-Control'], 'no-store')
        self.assertRedirects(self.client.get('/owner'), '/admin', fetch_redirect_response=False)
        self.client.force_login(self.owner)
        self.assertEqual(self.client.get('/owner').status_code, 200)
        self.assertRedirects(self.client.get('/admin'), '/owner', fetch_redirect_response=False)

    def test_api_aliases_never_expose_aggregates_or_payment_series_to_admin(self):
        for prefix in ('/api/admin', '/api/owner'):
            with self.subTest(prefix=prefix):
                response = self.client.get(prefix + '/overview')
                self.assertEqual(response.status_code, 200)
                self.assertEqual(response['Cache-Control'], 'no-store')
                data = response.json()
                self.assertNotIn('todayPayments', data['metrics'])
                self.assertNotIn('monthPayments', data['metrics'])
                self.assertTrue(all('payments' not in day for day in data['series']))
                self.assertEqual(data['metrics']['debt'], 90)
                self.assertEqual(data['payments'][0]['amount'], 123)
                directory = self.client.get(prefix + '/members').json()['members']
                self.assertTrue(directory)
                self.assertTrue(all('payment' not in row for row in directory))
                self.assertTrue(all(row['role'] not in {'admin', 'owner'} for row in directory))

    def test_admin_cannot_create_or_change_plans_or_member_payment_or_role(self):
        for prefix in ('/api/admin', '/api/owner'):
            self.assertEqual(self.client.post(prefix + '/plans', data=json.dumps({'price': 2000}), content_type='application/json').status_code, 403)
            self.assertEqual(self.client.patch(prefix + f'/plans/{self.plan.pk}', data=json.dumps({'price': 2000}), content_type='application/json').status_code, 403)
            for field, value in (('payment', 999), ('planId', self.plan.pk), ('role', 'owner'), ('is_superuser', True)):
                with self.subTest(prefix=prefix, field=field):
                    response = self.client.patch(prefix + f'/members/gym/{self.gym.pk}',
                        data=json.dumps({field: value, 'firstName': 'MustNotSave'}), content_type='application/json')
                    self.assertEqual(response.status_code, 403)
        self.assertFalse(GymRemoteCommand.objects.exists())
        self.gym.refresh_from_db()
        self.assertEqual(self.gym.first_name, 'Test')
        self.plan.refresh_from_db()
        self.assertEqual(self.plan.price, 1000)

    def test_admin_can_edit_member_and_debt_and_toggle_member_web_status(self):
        response = self.client.patch(f'/api/admin/members/gym/{self.gym.pk}',
            data=json.dumps({'firstName': 'Edited', 'debt': 45}), content_type='application/json')
        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.json()['queued'])
        self.assertEqual(GymRemoteCommand.objects.get().data, {'first_name': 'Edited', 'debt': 45})
        response = self.client.patch(f'/api/admin/users/{self.member.pk}/status',
            data=json.dumps({'status': 'suspended'}), content_type='application/json')
        self.assertEqual(response.status_code, 200)
        self.member.refresh_from_db()
        self.assertEqual(self.member.status, 'suspended')

    def test_protected_accounts_and_django_admin_cannot_bypass_limits(self):
        for user in (self.owner, self.admin):
            self.assertNotEqual(self.client.patch(f'/api/admin/users/{user.pk}/status',
                data=json.dumps({'status': 'suspended'}), content_type='application/json').status_code, 200)
            self.assertEqual(self.client.patch(f'/api/admin/members/web/{user.pk}',
                data=json.dumps({'firstName': 'Blocked'}), content_type='application/json').status_code, 403)
        self.assertFalse(admin.site.has_permission(SimpleNamespace(user=self.admin)))
        for path in ('/django-admin/', '/django-admin/members/plan/', f'/django-admin/members/plan/{self.plan.pk}/change/'):
            self.assertEqual(self.client.get(path).status_code, 302)
        self.assertTrue(admin.site.has_permission(SimpleNamespace(user=self.owner)))

    def test_owner_keeps_full_financial_insights(self):
        self.client.force_login(self.owner)
        data = self.client.get('/api/owner/overview').json()
        self.assertEqual(data['metrics']['todayPayments'], 123)
        self.assertTrue(all('payments' in day for day in data['series']))
        self.assertTrue(any(row['payment'] == 800 for row in self.client.get('/api/owner/members').json()['members']))

    def test_members_coaches_staff_and_suspended_admin_are_denied(self):
        for role, status in (('member', 'active'), ('coach', 'active'), ('staff', 'active'), ('admin', 'suspended')):
            user = User.objects.create_user(mobile=f'0912888{User.objects.count():04}', role=role, status=status)
            client = Client()
            client.force_login(user)
            for path in ('/api/admin/members', '/api/admin/overview', '/api/admin/plans', '/api/admin/activity'):
                self.assertEqual(client.get(path).status_code, 403)
            self.assertEqual(client.get('/admin').status_code, 302)

    def test_data_migration_preserves_existing_owner_accounts_only(self):
        migration = importlib.import_module('members.migrations.0010_owner_role')
        self.owner.role = 'admin'
        self.owner.save(update_fields=['role'])
        from django.apps import apps
        from django.db import connection
        migration.preserve_existing_owners(apps, SimpleNamespace(connection=connection))
        self.owner.refresh_from_db()
        self.admin.refresh_from_db()
        self.assertEqual(self.owner.role, 'owner')
        self.assertEqual(self.admin.role, 'admin')
