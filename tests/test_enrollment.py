import sqlite3
import tempfile
import unittest
from contextlib import closing
from pathlib import Path
from unittest.mock import Mock

from app.data.enrollments import EnrollmentRepository
from app.data.members import MembersRepository
from app.domain.models import MembershipApplication, PaymentReceipt
from app.domain.errors import FitTrackError
from app.services.enrollment import EnrollmentService

from tests.test_repositories import MEMBERS_SCHEMA


class StubApi:
    def __init__(self, fail_once=False):
        self.fail_once = fail_once
        self.calls = []

    def activate(self, application_id, member_id, paid_amount):
        self.calls.append((application_id, member_id, paid_amount))
        if self.fail_once:
            self.fail_once = False
            raise RuntimeError("temporary API failure")
        return {"ok": True}


class StubPos:
    def charge(self, amount):
        return PaymentReceipt(True, amount, "TEST-REF", "ok")


class EnrollmentTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(ignore_cleanup_errors=True)
        root = Path(self.temp.name)
        self.members_path = root / "members.db"
        with closing(sqlite3.connect(self.members_path)) as connection:
            connection.execute(MEMBERS_SCHEMA)
            connection.commit()
        self.workflows = EnrollmentRepository(root / "state.db")
        self.members = MembersRepository(self.members_path)
        self.application = MembershipApplication(
            id=17,
            full_name="مینا رضایی",
            first_name="مینا",
            last_name="رضایی",
            mobile="09121111111",
            national_id="0012345678",
            address="تهران، خیابان نمونه",
            plan="بدنسازی ۱۲ جلسه",
            plan_id=2,
            gender="female",
            price=2_400_000,
            requested_at="2026-08-12T10:00:00",
            status="pending",
        )

    def tearDown(self):
        self.temp.cleanup()

    def _service(self, api):
        return EnrollmentService(api, self.workflows, self.members, StubPos())

    def _prepare(self, service):
        service.start(self.application)
        service.save_face(self.application.id, [0.1, 0.2], b"jpeg-face")
        service.take_payment(self.application)

    def test_complete_creates_legacy_member_and_activates_site(self):
        api = StubApi()
        service = self._service(api)
        self._prepare(service)
        member_id = service.complete(
            self.application,
            {"father_name": "علی", "certificate_no": "44", "age": 27, "gender": "زن"},
        )
        self.assertEqual(api.calls, [(17, member_id, 2_400_000)])
        self.assertEqual(self.workflows.get(17).status, "activated")
        self.assertIsNone(self.workflows.biometric_payload(17))
        member = self.members.get(member_id)
        self.assertEqual(member.mobile, "09121111111")
        self.assertEqual(member.payment, 2_400_000)

    def test_recorded_payment_is_not_charged_twice(self):
        service = self._service(StubApi())
        service.start(self.application)
        service.pos = Mock()
        service.pos.charge.return_value = PaymentReceipt(True, self.application.price, "12345", "ok")
        first = service.take_payment(self.application)
        second = service.take_payment(self.application)
        self.assertEqual(first.reference, second.reference)
        service.pos.charge.assert_called_once_with(self.application.price)

    def test_declined_payment_does_not_mark_application_paid(self):
        service = self._service(StubApi())
        service.start(self.application)
        service.pos = Mock()
        service.pos.charge.return_value = PaymentReceipt(False, self.application.price, "", "declined")
        with self.assertRaises(FitTrackError):
            service.take_payment(self.application)
        self.assertEqual(self.workflows.get(self.application.id).paid_amount, 0)

    def test_retry_after_api_failure_does_not_duplicate_member(self):
        api = StubApi(fail_once=True)
        service = self._service(api)
        self._prepare(service)
        with self.assertRaises(RuntimeError):
            service.complete(self.application, {"gender": "زن"})
        first_state = self.workflows.get(17)
        self.assertEqual(first_state.status, "member_created")
        member_id = service.complete(self.application, {"gender": "زن"})
        self.assertEqual(member_id, first_state.legacy_member_id)
        with closing(sqlite3.connect(self.members_path)) as connection:
            count = connection.execute("SELECT COUNT(*) FROM users").fetchone()[0]
        self.assertEqual(count, 1)


if __name__ == "__main__":
    unittest.main()
