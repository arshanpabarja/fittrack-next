import json

from django.test import TestCase, override_settings

from .models import GymRemoteCommand, GymSyncCursor, GymSyncRecord, LegacyMember, MembershipApplication, Plan, User


@override_settings(FITTRACK_REMOTE_SYNC=True, FITTRACK_SYNC_SOURCE='test-gym', FITTRACK_DESKTOP_API_TOKEN='s' * 40)
class CloudSyncTests(TestCase):
    def post(self, records, sequence=1, source='test-gym', token='s' * 40, command_results=None):
        body = dict(source=source, sequence=sequence, records=records)
        if command_results is not None:
            body['commandResults'] = command_results
        return self.client.post('/api/desktop/sync', data=json.dumps(body),
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

    def test_distinct_plan_ids_can_share_names_and_retry_independently(self):
        male = self.record('plan', 12)
        female = self.record('plan', 13)
        female['data']['gender'] = 'female'
        female['data']['price'] = 200
        another = self.record('plan', 14)
        for _ in range(2):
            self.assertEqual(self.post([male, female, another]).status_code, 200)
        self.assertEqual(Plan.objects.filter(name='Gym 12').count(), 3)
        user = User.objects.create_user(mobile='09124445566')
        application = MembershipApplication.objects.create(user=user, plan_id=13)
        male['data']['price'] = 150
        self.assertEqual(self.post([male], sequence=2).status_code, 200)
        application.refresh_from_db()
        self.assertEqual(application.plan_id, 13)
        self.assertEqual(application.plan.price, 200)
        self.assertEqual(Plan.objects.get(pk=12).price, 150)

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

    def test_owner_shows_mirrored_attendance_and_queues_edits(self):
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
        overview = self.client.get('/api/owner/overview').json()
        self.assertTrue(overview['attendanceAvailable'])
        self.assertEqual(overview['metrics']['todayAttendance'], 1)
        self.assertEqual(overview['metrics']['inside'], 1)
        self.assertEqual(overview['members'][0]['lastVisit'], timezone.localdate().isoformat())
        edit = self.client.patch('/api/owner/members/gym/51',
            data=json.dumps({'firstName': 'Edited'}), content_type='application/json')
        self.assertEqual(edit.status_code, 200)
        self.assertTrue(edit.json()['queued'])
        command_response = self.post([], sequence=2).json()
        self.assertEqual(command_response['commands'][0]['data'], {'first_name': 'Edited'})
        command_id = command_response['commands'][0]['id']
        changed = self.record()
        changed['data']['first_name'] = 'Edited'
        ack = self.post([changed], sequence=3,
                        command_results=[{'id': command_id, 'success': True, 'error': ''}]).json()
        self.assertEqual(ack['resultAcks'], [command_id])
        self.assertEqual(GymRemoteCommand.objects.get(pk=command_id).status, 'applied')

    def test_online_plan_create_is_delivered_to_desktop(self):
        admin = User.objects.create_superuser(mobile='09129999998', password='not-used')
        self.client.force_login(admin)
        response = self.client.post('/api/owner/plans', data=json.dumps({
            'name': 'آنلاین ۸ جلسه در ماه', 'price': 500,
            'sessionsPerMonth': 8, 'gender': 'all', 'isActive': True,
        }), content_type='application/json')
        self.assertEqual(response.status_code, 200, response.content)
        command = GymRemoteCommand.objects.get(kind='plan')
        delivered = self.post([], sequence=1).json()['commands'][0]
        self.assertEqual(delivered['localId'], command.local_id)
        self.assertTrue(delivered['create'])
