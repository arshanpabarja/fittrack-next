import json
from datetime import timedelta

from django.test import TestCase, override_settings
from django.utils import timezone

from app.domain.dates import jalali_now
from .models import (Assessment, CoachNote, CoachProfile, GymSyncCursor, GymSyncRecord,
                     LegacyMember, MemberRequest, MemberWorkout, MembershipApplication, Plan,
                     TrainingSession, User, WorkoutProgram)


@override_settings(FITTRACK_REMOTE_SYNC=True, PASSWORD_HASHERS=['django.contrib.auth.hashers.MD5PasswordHasher'])
class MemberPanelTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.plan = Plan.objects.create(name='بدنسازی خصوصی ۲۴ جلسه', sessions_per_month=24)
        cls.coach = User.objects.create_user(mobile='09120000001', first_name='امین', last_name='تهرانی', role='coach', status='active')
        CoachProfile.objects.create(user=cls.coach, specialty='بدنسازی').allowed_plans.add(cls.plan)
        cls.member = cls.make_member('09120000002', 701)
        cls.peer = cls.make_member('09120000003', 702)
        cls.program = WorkoutProgram.objects.create(member=cls.member, coach=cls.coach, title='افزایش عضله', exercises='', coach_notes='راهنمای عمومی برنامه',
            schedule_json=[dict(weekday='thursday', label='روز فشار', exercises=[dict(name='پرس سینه', sets=2, reps='8-10', rest=90, weight=80, rpe=8, rir=2, note='کنترل حرکت')])])
        Assessment.objects.create(member=cls.member, coach=cls.coach, weight=79.2, waist=82)
        Assessment.objects.create(member=cls.peer, coach=cls.coach, weight=88, fitness_notes='private-peer-assessment')
        CoachNote.objects.create(member=cls.member, coach=cls.coach, content='private-coach-note')
        GymSyncCursor.objects.create(source='test', sequence=1)
        for local_id, member_id in [(1, 701), (2, 702)]:
            GymSyncRecord.objects.create(kind='attendance', local_id=local_id, data=dict(member_id=member_id, checked_in_at=timezone.localdate().isoformat() + ' 18:42:00', checked_out_at=None, full_name='private-device-name'))
            GymSyncRecord.objects.create(kind='renewal', local_id=local_id, data=dict(id=local_id, member_id=member_id, new_plan='بدنسازی خصوصی ۲۴ جلسه', paid_amount=2400000 + local_id, payment_reference=f'ref-{member_id}', renewed_at=timezone.now().isoformat()))
        TrainingSession.objects.create(member=cls.member, coach=cls.coach, scheduled_at=timezone.now() + timedelta(days=1), training_day='روز فشار')
        TrainingSession.objects.create(member=cls.peer, coach=cls.coach, scheduled_at=timezone.now() + timedelta(days=1), training_day='peer-private-session')

    @classmethod
    def make_member(cls, mobile, gym_id):
        member = User.objects.create_user(mobile=mobile, password='StrongPassword482!', first_name='آرشان', last_name='پابرجا', role='member', status='active')
        LegacyMember.objects.create(id=gym_id, first_name=member.first_name, last_name=member.last_name, mobile=mobile, gender='مرد', age=28,
            plan=cls.plan.name, used_sessions=16, signup_time=jalali_now(timezone.localtime().replace(tzinfo=None)), debt=0, payment=2400000,
            embedding='secret-embedding', face_image=b'secret-biometric-image')
        MembershipApplication.objects.create(user=member, plan=cls.plan, status='active', legacy_member_id=gym_id, face_registered=True)
        return member

    def setUp(self):
        self.client.force_login(self.member)

    def send(self, path, data, method='post'):
        return getattr(self.client, method)(path, json.dumps(data), content_type='application/json')

    def start(self):
        response = self.send('/api/member/workouts', dict(dayIndex=0))
        self.assertEqual(response.status_code, 201, response.content)
        return response.json()['workout']

    def test_workspace_is_personal_and_uses_device_membership(self):
        response = self.client.get('/api/member/workspace')
        self.assertEqual(response.status_code, 200, response.content)
        data = response.json()
        self.assertEqual(data['membership']['remaining'], 8)
        self.assertEqual(data['membership']['status'], 'active')
        self.assertGreater(data['membership']['daysLeft'], 20)
        self.assertEqual(data['attendance']['total'], 1)
        self.assertEqual(data['coach']['name'], 'امین تهرانی')
        self.assertNotIn('assessments', data)
        self.assertFalse(any(n['view'] == 'assessments' for n in data['notifications']))
        self.assertEqual(len(data['sessions']), 1)
        self.assertEqual(len(data['payments']), 1)
        self.assertNotContains(response, 'secret-biometric')
        for private in ('secret-embedding', 'face_image', 'embedding', 'private-coach-note', 'private-peer-assessment', 'peer-private-session', 'ref-702', 'private-device-name'):
            self.assertNotContains(response, private)
        self.assertIn('no-store', response['Cache-Control'])

    def test_member_dashboard_has_no_assessment_sections_or_bootstrap_data(self):
        response = self.client.get('/dashboard')
        self.assertNotContains(response, 'data-view="assessments"')
        self.assertNotContains(response, 'data-view="progress"')
        self.assertNotContains(response, 'ارزیابی')
        self.assertNotContains(response, 'body_fat')
        self.assertEqual(Assessment.objects.filter(member=self.member).count(), 1)

    def test_anonymous_inactive_and_other_roles_cannot_use_member_endpoints(self):
        self.client.logout()
        self.assertEqual(self.client.get('/dashboard').status_code, 302)
        self.assertEqual(self.client.get('/api/member/workspace').status_code, 401)
        self.client.force_login(self.coach)
        self.assertEqual(self.client.get('/api/member/workspace').status_code, 403)
        self.member.status = 'suspended'
        self.member.save()
        self.client.force_login(self.member)
        self.assertEqual(self.client.get('/api/member/workspace').status_code, 403)
        self.assertEqual(self.send('/api/member/requests', dict(kind='general', message='test')).status_code, 403)

    def test_workout_resume_persistence_and_coach_review(self):
        workout = self.start()
        self.assertEqual(self.send('/api/member/workouts', dict(dayIndex=0)).json()['workout']['id'], workout['id'])
        exercises = workout['exercises']
        exercises[0]['sets'][0] = dict(weight=80, reps=10, complete=True)
        response = self.send(f'/api/member/workouts/{workout["id"]}', dict(exercises=exercises, note='تمرین خوب بود', finish=True), 'patch')
        self.assertEqual(response.status_code, 200, response.content)
        self.assertIsNotNone(response.json()['workout']['finishedAt'])
        self.program.refresh_from_db()
        self.assertEqual(self.program.schedule_json[0]['exercises'][0]['sets'], 2)
        self.client.force_login(self.coach)
        response = self.client.get(f'/api/coach/clients/{self.member.pk}')
        self.assertEqual(response.status_code, 200, response.content)
        self.assertEqual(response.json()['workouts'][0]['exercises'][0]['sets'][0]['reps'], 10)

    def test_workout_can_finish_without_set_logging_or_fabricated_results(self):
        workout = self.start()
        response = self.send(f'/api/member/workouts/{workout["id"]}', dict(finish=True), 'patch')
        self.assertEqual(response.status_code, 200, response.content)
        result = response.json()['workout']
        self.assertIsNotNone(result['finishedAt'])
        self.assertEqual(result['exercises'], workout['exercises'])
        self.assertFalse(any(s['complete'] for e in result['exercises'] for s in e['sets']))
        self.assertTrue(all(s['reps'] is None for e in result['exercises'] for s in e['sets']))
        self.assertEqual(self.send(f'/api/member/workouts/{workout["id"]}', dict(finish=True), 'patch').status_code, 409)
        self.assertNotEqual(self.start()['id'], workout['id'])

    def test_invalid_logs_structure_edits_and_peer_access_are_rejected(self):
        workout = self.start()
        path = f'/api/member/workouts/{workout["id"]}'
        self.assertEqual(self.send(path, dict(exercises=[]), 'patch').status_code, 400)
        exercises = workout['exercises']
        exercises[0]['sets'][0] = dict(weight=None, reps=10, complete=True)
        self.assertEqual(self.send(path, dict(exercises=exercises), 'patch').status_code, 400)
        exercises[0]['sets'][0] = dict(weight=-2, reps=10, complete=True)
        self.assertEqual(self.send(path, dict(exercises=exercises), 'patch').status_code, 400)
        self.client.force_login(self.peer)
        self.assertEqual(self.send(path, dict(note='tampering'), 'patch').status_code, 404)
        self.assertEqual(self.client.get('/api/member/workspace').json()['workouts'], [])

    def test_request_preferences_and_receipts_belong_to_current_member(self):
        result = self.send('/api/member/requests', dict(kind='freeze', message='از هفته آینده'))
        self.assertEqual(result.status_code, 201)
        self.assertEqual(MemberRequest.objects.get().member, self.member)
        self.assertEqual(self.send('/api/member/requests', dict(kind='invalid', message='test')).status_code, 400)
        self.assertEqual(self.send('/api/member/preferences', dict(notificationsEnabled=False), 'patch').status_code, 200)
        self.assertFalse(self.client.get('/api/member/workspace').json()['notificationsEnabled'])
        receipt = self.client.get('/api/member/receipts/1')
        self.assertEqual(receipt.status_code, 200)
        self.assertContains(receipt, 'ref-701')
        self.assertEqual(self.client.get('/api/member/receipts/2').status_code, 404)
        self.client.force_login(self.peer)
        self.assertEqual(self.client.get('/api/member/workspace').json()['requests'], [])
        self.assertEqual(self.client.get('/api/member/receipts/1').status_code, 404)

    def test_no_program_is_an_empty_state_and_cannot_start(self):
        self.client.force_login(self.peer)
        self.assertIsNone(self.client.get('/api/member/workspace').json()['program'])
        self.assertEqual(self.send('/api/member/workouts', dict(dayIndex=0)).status_code, 409)

    def test_password_change_keeps_current_session_and_rejects_wrong_current_password(self):
        self.assertEqual(self.send('/api/member/account', dict(action='password', currentPassword='wrong', newPassword='FreshSecurePassword729!')).status_code, 400)
        response = self.send('/api/member/account', dict(action='password', currentPassword='StrongPassword482!', newPassword='FreshSecurePassword729!'))
        self.assertEqual(response.status_code, 200)
        self.member.refresh_from_db()
        self.assertTrue(self.member.check_password('FreshSecurePassword729!'))
        self.assertEqual(self.client.get('/api/member/workspace').status_code, 200)

    def test_csrf_is_required_for_mutations(self):
        from django.test import Client
        protected = Client(enforce_csrf_checks=True)
        protected.force_login(self.member)
        self.assertEqual(protected.post('/api/member/requests', json.dumps(dict(kind='general', message='test')), content_type='application/json').status_code, 403)

    def test_bootstrap_is_authenticated_and_escapes_script_text(self):
        self.member.first_name = '</script><script>window.attack=true</script>'
        self.member.save(update_fields=['first_name'])
        response = self.client.get('/dashboard')
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'id="member-bootstrap"')
        self.assertNotContains(response, '<script>window.attack=true</script>')
        self.assertIn('no-store', response['Cache-Control'])
        self.client.logout()
        response = self.client.get('/dashboard')
        self.assertEqual(response.status_code, 302)
        self.assertNotContains(response, 'member-bootstrap', status_code=302)

    def test_logout_others_preserves_current_session_and_other_members(self):
        from django.test import Client
        other_device, peer_device = Client(), Client()
        other_device.force_login(self.member)
        peer_device.force_login(self.peer)
        response = self.send('/api/member/account', dict(action='logout_others'))
        self.assertEqual(response.status_code, 200)
        self.assertEqual(self.client.get('/api/member/workspace').status_code, 200)
        self.assertEqual(other_device.get('/api/member/workspace').status_code, 401)
        self.assertEqual(peer_device.get('/api/member/workspace').status_code, 200)

    def test_receipt_id_is_stable_when_a_new_synced_payment_arrives(self):
        self.assertContains(self.client.get('/api/member/receipts/1'), 'ref-701')
        GymSyncRecord.objects.create(kind='renewal', local_id=400, data=dict(member_id=701, new_plan='نیمه‌خصوصی ۸ جلسه', paid_amount=100, payment_reference='new-payment', renewed_at=timezone.now().isoformat()))
        self.assertContains(self.client.get('/api/member/receipts/1'), 'ref-701')
        self.assertContains(self.client.get('/api/member/receipts/400'), 'new-payment')

    def test_member_startup_is_compressed_without_changing_cache_protection(self):
        import gzip
        response = self.client.get('/dashboard', HTTP_ACCEPT_ENCODING='gzip')
        self.assertEqual(response['Content-Encoding'], 'gzip')
        self.assertIn('no-store', response['Cache-Control'])
        self.assertIn(b'member-bootstrap', gzip.decompress(response.content))
        response = self.client.get('/member.js', HTTP_ACCEPT_ENCODING='gzip')
        self.assertEqual(response['Content-Encoding'], 'gzip')
        self.assertIn(b'member-bootstrap', gzip.decompress(b''.join(response.streaming_content)))
