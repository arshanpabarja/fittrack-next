import json
from datetime import timedelta

from django.test import Client, SimpleTestCase, TestCase, override_settings
from django.utils import timezone

from .models import (Assessment, CoachNote, CoachProfile, Exercise, GymSyncCursor, GymSyncRecord,
                     LegacyMember, MembershipApplication, Plan, ProgramRevision, TrainingProfile,
                     TrainingSession, User, WorkoutProgram)


@override_settings(FITTRACK_REMOTE_SYNC=True, PASSWORD_HASHERS=['django.contrib.auth.hashers.MD5PasswordHasher'])
class CoachingTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.plan = Plan.objects.create(name='نیمه‌خصوصی ۸ جلسه', sessions_per_month=8)
        cls.other_plan = Plan.objects.create(name='خصوصی ۱۲ جلسه', sessions_per_month=12)
        cls.coach = User.objects.create_user(mobile='09120000001', first_name='امین', role='coach', status='active')
        cls.other_coach = User.objects.create_user(mobile='09120000002', role='coach', status='active')
        for coach in (cls.coach, cls.other_coach):
            CoachProfile.objects.create(user=coach).allowed_plans.add(cls.plan)
        cls.member = cls.make_member('09120000003', cls.plan, 'علی', 7101)
        cls.peer = cls.make_member('09120000004', cls.plan, 'سارا', 7102)
        cls.outsider = cls.make_member('09120000005', cls.other_plan, 'خارج', 7103)
        GymSyncCursor.objects.create(source='test', sequence=1)
        GymSyncRecord.objects.create(kind='attendance', local_id=1, data=dict(member_id=7101,
            checked_in_at=(timezone.localdate() - timedelta(days=14)).isoformat() + ' 10:00:00',
            checked_out_at=None, mobile='sensitive-phone', full_name='ignored-name', locker_id=12))
        GymSyncRecord.objects.create(kind='attendance', local_id=2, data=dict(member_id=7103,
            checked_in_at=timezone.now().isoformat(), checked_out_at=None, mobile='outsider-phone'))

    @classmethod
    def make_member(cls, mobile, plan, name, gym_id):
        user = User.objects.create_user(mobile=mobile, first_name=name, role='member', status='active',
                                        national_id='secret-' + mobile, address='secret-address')
        gym = LegacyMember.objects.create(id=gym_id, first_name=name, last_name='رضایی', mobile=mobile,
            gender='مرد', age=29, plan=plan.name, used_sessions=6, signup_time=timezone.localdate().isoformat() + ' 09:00:00',
            father_name='secret-father', certificate_no='secret-certificate', debt=950, payment=2500)
        MembershipApplication.objects.create(user=user, plan=plan, status='active', legacy_member_id=gym.pk,
                                            activated_at=timezone.now(), face_registered=True, paid_amount=2500)
        return user

    def setUp(self):
        self.client.force_login(self.coach)

    def send(self, path, data, method='post'):
        return getattr(self.client, method)(path, data=json.dumps(data), content_type='application/json')

    def program(self, member=None, **extra):
        data = dict(memberId=(member or self.member).pk, title='ماه اول', mainGoal='strength',
                    startDate=timezone.localdate().isoformat(), endDate=(timezone.localdate() + timedelta(days=28)).isoformat(),
                    days=[dict(weekday='saturday', label='روز فشار', exercises=[dict(name='پرس سینه', sets=3, reps='8-10', weight=80, rest=90, rpe=8, rir=2, tempo='3-1-1', note='کنترل پایین رفتن')])])
        data.update(extra)
        response = self.send('/api/coach/training-programs', data)
        self.assertEqual(response.status_code, 200, response.content)
        return response.json()['program']

    def book(self, member=None, **extra):
        data = dict(memberId=(member or self.member).pk, scheduledAt=timezone.localdate().isoformat() + 'T10:00:00+03:30', dayIndex=0)
        data.update(extra)
        return self.send('/api/coach/sessions', data)

    def test_directory_allowlist_and_device_attendance(self):
        response = self.client.get('/api/coach/workspace')
        self.assertEqual(response.status_code, 200)
        self.assertIn('no-store', response['Cache-Control'])
        result = response.json()
        self.assertEqual({c['id'] for c in result['clients']}, {self.member.pk, self.peer.pk})
        member = next(c for c in result['clients'] if c['id'] == self.member.pk)
        self.assertEqual(member['sessionsRemaining'], 2)
        self.assertEqual(member['daysAbsent'], 14)
        self.assertTrue(member['faceRegistered'])
        self.assertTrue({'inactive', 'assessment', 'program', 'low_sessions'} <= {a['kind'] for a in member['alerts']})
        body = response.content.decode()
        for sensitive in ['secret-address', 'secret-father', 'secret-certificate', 'sensitive-phone', 'outsider-phone', self.member.mobile, 'paidAmount', 'password', 'nationalId']:
            self.assertNotIn(sensitive, body)
        detail = self.client.get(f'/api/coach/clients/{self.member.pk}').json()
        self.assertEqual(detail['visitCount'], 1)
        self.assertEqual(set(detail['attendance'][0]), {'checkIn', 'checkOut'})

    def test_client_and_record_permissions_are_enforced(self):
        self.assertEqual(self.client.get(f'/api/coach/clients/{self.outsider.pk}').status_code, 404)
        self.assertEqual(self.send('/api/coach/assessments', dict(memberId=self.outsider.pk, date=timezone.localdate().isoformat(), weight=80)).status_code, 404)
        self.assertEqual(self.send('/api/coach/notes', dict(memberId=self.outsider.pk, content='note')).status_code, 404)
        for user in (self.member, self.outsider):
            self.client.force_login(user)
            self.assertEqual(self.client.get('/api/coach/workspace').status_code, 403)
        self.client.logout()
        self.assertEqual(self.client.get('/coach-panel').status_code, 302)

    def test_suspended_and_disabled_coaches_cannot_access(self):
        self.coach.status = 'suspended'; self.coach.save(update_fields=['status'])
        self.assertEqual(self.client.get('/api/coach/workspace').status_code, 403)
        self.coach.status = 'active'; self.coach.is_active = False; self.coach.save(update_fields=['status', 'is_active'])
        self.assertEqual(self.client.get('/api/coach/workspace').status_code, 403)

    def test_assessment_history_comparison_and_partial_values(self):
        for age, weight, waist, bench in [(32, 82.4, 91, 70), (0, 79.2, 86, 80)]:
            response = self.send('/api/coach/assessments', dict(memberId=self.member.pk,
                date=(timezone.localdate() - timedelta(days=age)).isoformat(), weight=weight, waist=waist, bench_press=bench))
            self.assertEqual(response.status_code, 201)
        detail = self.client.get(f'/api/coach/clients/{self.member.pk}').json()
        self.assertEqual(detail['comparison'], dict(weight=-3.2, waist=-5.0, bench_press=10.0))
        self.assertEqual(len(detail['assessments']), 2)
        self.assertFalse(any(a['kind'] == 'assessment' for a in detail['client']['alerts']))

    def test_assessment_and_profile_validation(self):
        base = dict(memberId=self.member.pk, date=timezone.localdate().isoformat())
        for extra in ({}, {'weight': 'NaN'}, {'weight': -1}, {'body_fat': 101}, {'pull_ups': 1.2}, {'weight': 80, 'date': (timezone.localdate() + timedelta(days=1)).isoformat()}):
            self.assertEqual(self.send('/api/coach/assessments', {**base, **extra}).status_code, 400)
        url = f'/api/coach/clients/{self.member.pk}'
        values = dict(main_goal='fat_loss', experience='beginner', frequency=3, injuries='کتف', reported_pain=True)
        self.assertEqual(self.send(url, values, 'patch').status_code, 200)
        self.assertTrue(TrainingProfile.objects.get().reported_pain)
        values['frequency'] = 8
        self.assertEqual(self.send(url, values, 'patch').status_code, 400)

    def test_program_versions_archive_and_member_compatibility(self):
        initial = self.program()
        self.program(title='ماه دوم')
        self.assertEqual(ProgramRevision.objects.get().snapshot['title'], 'ماه اول')
        self.assertEqual(WorkoutProgram.objects.count(), 1)
        self.client.force_login(self.member)
        self.assertEqual(self.client.get('/api/member/program').json()['program']['days'][0]['movements'], ['پرس سینه | 3 × 8-10'])
        self.client.force_login(self.coach)
        self.assertEqual(self.send(f"/api/coach/training-programs/{initial['id']}", {'action': 'archive'}, 'patch').status_code, 200)
        detail = self.client.get(f'/api/coach/clients/{self.member.pk}').json()
        self.assertIsNone(detail['client']['currentProgram'])
        self.assertEqual(len(detail['programHistory']), 2)
        self.client.force_login(self.member)
        self.assertIsNone(self.client.get('/api/member/program').json()['program'])

    def test_program_validation_and_replacement_do_not_erase_history(self):
        self.program()
        current = WorkoutProgram.objects.get()
        self.assertEqual(self.send('/api/coach/training-programs', dict(memberId=self.member.pk, mainGoal='strength', title='invalid', startDate='2026-10-10', endDate='2026-01-01', days=[])).status_code, 400)
        self.assertEqual(ProgramRevision.objects.count(), 0)
        self.assertEqual(current.title, 'ماه اول')

    def test_training_session_is_separate_from_attendance_and_session_allowance(self):
        self.program()
        response = self.book(); self.assertEqual(response.status_code, 201, response.content)
        session = response.json()['sessions'][0]
        log = session['exercises']; log[0]['sets'][0].update(weight=80, reps=10, complete=True)
        result = self.send(f"/api/coach/sessions/{session['id']}", dict(status='completed', exercises=log, notes='افزایش وزنه بعدی'), 'patch')
        self.assertEqual(result.status_code, 200, result.content)
        self.assertIsNotNone(result.json()['session']['completedAt'])
        self.assertEqual(LegacyMember.objects.get(pk=7101).used_sessions, 6)
        self.assertEqual(GymSyncRecord.objects.filter(kind='attendance').count(), 2)
        self.assertEqual(self.send(f"/api/coach/sessions/{session['id']}", {'status': 'in_progress'}, 'patch').status_code, 400)
        self.assertEqual(self.client.get('/api/coach/workspace').json()['performance']['completed'], 1)
        self.program(title='برنامه تازه')
        self.assertEqual(TrainingSession.objects.get().program_title, 'ماه اول')
        self.assertEqual(TrainingSession.objects.get().exercises[0]['sets'][0]['weight'], 80)

    def test_session_validation_conflicts_and_group_booking_are_atomic(self):
        self.program(); self.program(self.peer)
        response = self.book(memberIds=[self.member.pk, self.peer.pk], groupLabel='گروه قدرت')
        self.assertEqual(response.status_code, 201)
        self.assertEqual(TrainingSession.objects.count(), 2)
        self.assertEqual(self.book(scheduledAt=timezone.localdate().isoformat() + 'T10:30:00+03:30').status_code, 400)
        self.assertEqual(self.book(memberIds=[self.member.pk, self.outsider.pk], groupLabel='خارج', scheduledAt=timezone.localdate().isoformat() + 'T12:00:00+03:30').status_code, 404)
        self.assertEqual(TrainingSession.objects.count(), 2)
        self.assertEqual(self.book(dayIndex=6).status_code, 400)

    def test_session_set_validation_and_statuses(self):
        self.program(); session = self.book().json()['sessions'][0]
        log = session['exercises']; log[0]['sets'][0]['complete'] = True
        url = f"/api/coach/sessions/{session['id']}"
        self.assertEqual(self.send(url, {'exercises': log}, 'patch').status_code, 400)
        self.assertEqual(self.send(url, {'status': 'no_show'}, 'patch').status_code, 200)
        self.assertEqual(self.client.get('/api/coach/workspace').json()['metrics']['trainingToday'], 0)
        self.assertEqual(self.book().status_code, 201)

    def test_private_sessions_cannot_double_book_coach(self):
        self.program(); self.program(self.peer)
        self.assertEqual(self.book().status_code, 201)
        self.assertEqual(self.book(self.peer).status_code, 400)
        self.assertEqual(self.book(self.peer, scheduledAt=timezone.localdate().isoformat() + 'T11:00:00+03:30').status_code, 201)

    def test_notes_and_custom_exercises_remain_private_to_author(self):
        response = self.send('/api/coach/notes', dict(memberId=self.member.pk, content='private coaching note', reportedPain=True, followUpOn=timezone.localdate().isoformat()))
        self.assertEqual(response.status_code, 201)
        note_id = response.json()['note']['id']
        self.send('/api/coach/exercises', dict(name='custom-only', muscleGroup='legs', mediaUrl='https://example.com/exercise.mp4'))
        self.client.force_login(self.other_coach)
        self.assertEqual(self.client.get('/api/coach/notes').json()['notes'], [])
        self.assertNotIn('custom-only', self.client.get('/api/coach/exercises').content.decode())
        self.assertEqual(self.send(f'/api/coach/notes/{note_id}', {'resolved': True}, 'patch').status_code, 404)
        self.client.force_login(self.coach)
        self.assertEqual(self.send(f'/api/coach/notes/{note_id}', {'resolved': True}, 'patch').status_code, 200)
        self.assertTrue(CoachNote.objects.get().resolved)
        self.assertEqual(self.send('/api/coach/exercises', dict(name='bad', muscleGroup='legs', mediaUrl='javascript:alert(1)')).status_code, 400)

    def test_revoking_plan_hides_past_records_on_every_endpoint(self):
        self.program(); session = self.book().json()['sessions'][0]
        self.send('/api/coach/notes', dict(memberId=self.member.pk, content='private'))
        self.coach.coach_profile.allowed_plans.clear()
        self.assertEqual(self.client.get('/api/coach/workspace').json()['clients'], [])
        self.assertEqual(self.client.get('/api/coach/programs').json()['programs'], [])
        self.assertEqual(self.client.get('/api/coach/training-programs').json()['programs'], [])
        self.assertEqual(self.client.get('/api/coach/notes').json()['notes'], [])
        self.assertEqual(self.client.get(f"/api/coach/sessions/{session['id']}").status_code, 404)
        self.assertEqual(self.send(f"/api/coach/training-programs/{session['programId']}", {'action': 'archive'}, 'patch').status_code, 404)

    def test_csrf_and_malformed_request(self):
        csrf = Client(enforce_csrf_checks=True); csrf.force_login(self.coach)
        self.assertEqual(csrf.post('/api/coach/notes', data='{}', content_type='application/json').status_code, 403)
        self.assertEqual(self.client.post('/api/coach/notes', data='[]', content_type='application/json').status_code, 400)
        self.assertEqual(self.client.get('/api/coach/sessions?start=bad').status_code, 400)

    @override_settings(FITTRACK_ATTENDANCE_PATH=__import__('pathlib').Path('does-not-exist.db'), FITTRACK_REMOTE_SYNC=False)
    def test_missing_attendance_is_not_treated_as_inactivity(self):
        result = self.client.get('/api/coach/workspace').json()
        self.assertFalse(result['attendanceAvailable'])
        self.assertFalse(any(a['kind'] == 'inactive' for c in result['clients'] for a in c['alerts']))
        self.assertIsNone(result['performance']['attendanceRate'])

    def test_coach_page_and_assets(self):
        self.assertEqual(self.client.get('/coach-panel').status_code, 200)


class CoachAssetTests(SimpleTestCase):
    def test_assets_are_served(self):
        for path in ('/coach.js', '/coach.css'):
            response = self.client.get(path)
            self.assertEqual(response.status_code, 200)
            self.assertTrue(b''.join(response.streaming_content))
            response.close()
