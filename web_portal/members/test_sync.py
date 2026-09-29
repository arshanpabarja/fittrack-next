import json

from django.test import TestCase, override_settings

from .models import GymSyncCursor, GymSyncRecord, LegacyMember, MembershipApplication, Plan, User


@override_settings(FITTRACK_REMOTE_SYNC=True, FITTRACK_SYNC_SOURCE='test-gym', FITTRACK_DESKTOP_API_TOKEN='s' * 40)
class CloudSyncTests(TestCase):
    def post(self, records, sequence=1, source='test-gym', token='s' * 40):
        return self.client.post('/api/desktop/sync', data=json.dumps(dict(source=source, sequence=sequence, records=records)),
                                content_type='application/json', HTTP_AUTHORIZATION='Bearer ' + token)

    def record(self, kind='member', key=51):
        data = dict(first_name='Test', last_name='Member', father_name='', national_id='',
                    certificate_no='', address='', mobile='09121112233', age=25,
                    gender='male', plan='Gym 12', used_sessions=2, signup_time='1405/07/01',
                    debt=0, payment=100, face_registered=True)
        if kind == 'plan':
            data = dict(name='Gym 12', price=100, gender='male', sessions_per_month=12, is_active=True)
        return dict(kind=kind, id=key, data=data)

    def test_retry_and_order_do_not_duplicate_or_revert_members(self):
        record = self.record()
        self.assertEqual(self.post([record]).status_code, 200)
        self.assertEqual(self.post([record]).status_code, 200)
        self.assertEqual(LegacyMember.objects.filter(pk=51).count(), 1)
        record['data']['used_sessions'] = 3
        self.assertEqual(self.post([record]).status_code, 409)
        self.assertEqual(self.post([record], sequence=3).status_code, 409)
        self.assertEqual(self.post([record], sequence=2).status_code, 200)
        self.assertEqual(LegacyMember.objects.get(pk=51).used_sessions, 3)
        self.assertIsNone(LegacyMember.objects.get(pk=51).embedding)
        self.assertIsNone(LegacyMember.objects.get(pk=51).face_image)

    def test_credentials_source_and_biometrics_rejected(self):
        record = self.record()
        self.assertEqual(self.post([record], token='wrong').status_code, 401)
        self.assertEqual(self.post([record], source='different').status_code, 403)
        record['data']['embedding'] = [1, 2, 3]
        self.assertEqual(self.post([record]).status_code, 400)
        self.assertEqual(GymSyncCursor.objects.count(), 0)

    def test_batch_rollback_on_existing_plan_conflict(self):
        Plan.objects.create(pk=12, name='Another', price=1, sessions_per_month=1)
        self.assertEqual(self.post([self.record(), self.record('plan', 12)]).status_code, 409)
        self.assertFalse(LegacyMember.objects.filter(pk=51).exists())
        self.assertFalse(GymSyncCursor.objects.exists())

    def test_delete_known_member_and_deactivate_plan(self):
        self.assertEqual(self.post([self.record(), self.record('plan', 12)]).status_code, 200)
        deleted = [dict(kind='member', id=51, data=None), dict(kind='plan', id=12, data=None)]
        self.assertEqual(self.post(deleted, 2).status_code, 200)
        self.assertFalse(LegacyMember.objects.filter(pk=51).exists())
        self.assertFalse(Plan.objects.get(pk=12).is_active)

    def test_activation_retry_and_cloud_reconcile_without_face_upload(self):
        self.assertEqual(self.post([self.record(), self.record('plan', 12)]).status_code, 200)
        user = User.objects.create_user(mobile='09121112233', password='not-used')
        application = MembershipApplication.objects.create(user=user, plan_id=12)
        for _ in range(2):
            response = self.client.post(f'/api/desktop/applications/{application.id}/activate',
                data=json.dumps(dict(legacyMemberId=51, paidAmount=100)), content_type='application/json',
                HTTP_AUTHORIZATION='Bearer ' + 's' * 40)
            self.assertEqual(response.status_code, 200, response.content)
        application.refresh_from_db()
        self.assertEqual(application.status, 'active')

    def test_owner_shows_mirrored_attendance_and_blocks_edits(self):
        admin = User.objects.create_superuser(mobile='09129999999', password='not-used')
        self.client.force_login(admin)
        from django.utils import timezone
        at = timezone.localdate().isoformat() + ' 12:00:00'
        record = dict(kind='attendance', id=1, data=dict(member_id=51, full_name='Test', mobile='09121112233',
                      plan='Gym 12', checked_in_at=at, checked_out_at=None, locker_id=3))
        self.assertEqual(self.post([self.record(), record]).status_code, 200)
        response = self.client.get('/api/owner/activity').json()
        self.assertTrue(response['attendanceAvailable'])
        self.assertEqual(response['visitCount'], 1)
        self.assertEqual(response['inside'], 1)
        self.assertEqual(self.client.patch('/api/owner/members/gym/51', data='{}', content_type='application/json').status_code, 409)
