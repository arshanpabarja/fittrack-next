import unittest
from unittest.mock import Mock, patch

from app.domain.dates import membership_expires_at, membership_expired
from app.domain.errors import MembershipExpired
from app.domain.models import MemberDetails, PaymentReceipt
from app.services.attendance import AttendanceService
from app.services.members import MemberService


class ExpiryTests(unittest.TestCase):
    def member(self, used=2):
        return MemberDetails(1, "نام", "عضو", "09120000001", "", "پلن ۱۲ جلسه",
                             used, 0, "1405-06-01 10:00:00", "", "", "", None, "مرد", 100)

    def test_calendar_month_boundaries_and_end_of_year(self):
        self.assertEqual(membership_expires_at("2026-08-23 10:00:00"), "1405-07-01 10:00:00")
        self.assertEqual(membership_expires_at("1405/06/31 10:15"), "1405-07-30 10:15:00")
        self.assertEqual(membership_expires_at("1400/11/30"), "1400-12-29 00:00:00")
        self.assertEqual(membership_expires_at("1399/11/30"), "1399-12-30 00:00:00")
        self.assertEqual(membership_expires_at("1404/12/29"), "1405-01-29 00:00:00")
        with patch("app.domain.dates.jalali_now", return_value="1405-07-01 09:59:59"):
            self.assertFalse(membership_expired("1405-06-01 10:00:00"))
        with patch("app.domain.dates.jalali_now", return_value="1405-07-01 10:00:00"):
            self.assertTrue(membership_expired("1405-06-01 10:00:00"))

    @patch("app.domain.dates.jalali_now", return_value="1405-07-01 10:00:00")
    def test_expired_positive_and_negative_sessions_are_blocked_without_mutation(self, clock):
        for used in (2, 10, 12, 14, 17):
            with self.subTest(used=used):
                face, attendance, members, access = Mock(), Mock(), Mock(), Mock()
                face.match.return_value = Mock(id=1)
                members.get.return_value = self.member(used)
                service = AttendanceService(face, attendance, members, access)
                with self.assertRaises(MembershipExpired) as raised:
                    service.check_in([1, 0])
                self.assertEqual(raised.exception.member_id, 1)
                attendance.check_in.assert_not_called()
                members.increment_used_sessions.assert_not_called()
                access.open_entry.assert_not_called()
                self.assertTrue(members.get.return_value.renewal_required)

    @patch("app.domain.dates.jalali_now", return_value="1405-07-01 10:00:00")
    @patch("app.services.members.jalali_now", return_value="1405-07-01 10:00:00")
    def test_expired_renewal_starts_now_without_carrying_unused_sessions(self, *mocks):
        for used, expected_carried in ((2, 0), (14, 2)):
            repository, history, pos = Mock(), Mock(), Mock()
            repository.get.return_value = self.member(used)
            history.grace_started_at.return_value = "1405-06-20 10:00:00"
            pos.charge.return_value = PaymentReceipt(True, 100, "123", "ok")
            result = MemberService(repository, history, pos).renew_member(1, "پلن ۱۲ جلسه", 100)
            self.assertEqual(result.membership_started_at, "1405-07-01 10:00:00")
            self.assertEqual(result.carried_sessions, expected_carried)
            self.assertEqual(repository.renew_membership.call_args.kwargs['carried_sessions'], expected_carried)
