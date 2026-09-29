import json
import sqlite3
import tempfile
import unittest
from contextlib import closing
from pathlib import Path
from unittest.mock import Mock

from app.data.attendance import AttendanceRepository
from app.data.memberships import MembershipRepository
from app.domain.models import SignupPlan
from app.services.cloud_sync import CloudSyncService
from tests.test_repositories import MEMBERS_SCHEMA


class CloudQueueTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        root = Path(self.temp.name)
        self.members, self.state = root / 'members.db', root / 'state.db'
        with closing(sqlite3.connect(self.members)) as conn:
            conn.execute(MEMBERS_SCHEMA)
            conn.execute("INSERT INTO users (first_name,last_name,mobile,gender,plan,signup_time,embedding,face_image) VALUES ('A','B','09121112233','male','Gym 12','1405/07/01','secret-vector',X'010203')")
            conn.commit()
        AttendanceRepository(self.state)
        MembershipRepository(self.state)
        self.plans = Mock()
        self.plans.load.return_value = (SignupPlan(12, 'Gym 12', 100, 'male', 12),)
        self.api = Mock(base_url='https://lifeboxgym.com', token='s'*40)
        self.api._request.side_effect = lambda method, path, body: dict(ok=True, sequence=body['sequence'])

    def service(self):
        return CloudSyncService(self.api, self.members, self.state, self.plans, 'test-gym')

    def test_network_loss_replays_identical_persisted_batch_after_restart(self):
        service = self.service()
        self.api._request.side_effect = TimeoutError('lost reply')
        with self.assertRaises(TimeoutError):
            service.run()
        first = self.api._request.call_args.args[2]
        with closing(sqlite3.connect(self.members)) as conn:
            conn.execute('UPDATE users SET used_sessions=3')
            conn.commit()
        self.api._request.side_effect = lambda method, path, body: dict(ok=True, sequence=body['sequence'])
        self.service().run()
        bodies = [call.args[2] for call in self.api._request.call_args_list]
        self.assertEqual(bodies[1], first)
        self.assertEqual(bodies[2]['sequence'], 2)
        self.assertEqual(bodies[2]['records'][0]['data']['used_sessions'], 3)
        self.assertNotIn('secret-vector', json.dumps(bodies))
        self.assertNotIn('face_image', json.dumps(bodies))
        self.assertTrue(first['records'][0]['data']['face_registered'])
        self.api._request.reset_mock()
        self.assertEqual(self.service().run(), 0)
        self.assertEqual(self.api._request.call_count, 1)
        self.assertEqual(self.api._request.call_args.args[2]['records'], [])

    def test_checkout_changes_and_deletions_are_replicated(self):
        with closing(sqlite3.connect(self.state)) as conn:
            conn.execute("INSERT INTO attendance_sessions (member_id,full_name,mobile,plan) VALUES (1,'A B','09121112233','Gym 12')")
            conn.commit()
        service = self.service()
        service.run()
        with closing(sqlite3.connect(self.state)) as conn:
            conn.execute("UPDATE attendance_sessions SET checked_out_at='2026-09-29 13:00:00'")
            conn.commit()
        with closing(sqlite3.connect(self.members)) as conn:
            conn.execute('DELETE FROM users')
            conn.commit()
        service.run()
        batch = self.api._request.call_args_list[-2].args[2]
        self.assertIn(dict(kind='member', id=1, data=None), batch['records'])
        self.assertEqual(batch['records'][0]['data']['checked_out_at'], '2026-09-29 13:00:00')

    def test_identity_change_and_http_are_rejected(self):
        self.service()
        with self.assertRaises(Exception):
            CloudSyncService(self.api, self.members, self.state, self.plans, 'another-gym')
        self.api.base_url = 'http://lifeboxgym.com'
        with self.assertRaises(Exception):
            self.service()
