import unittest

from app.domain.dates import validate_membership_datetime


class MembershipDateEditTests(unittest.TestCase):
    def test_persian_and_gregorian_dates(self):
        self.assertEqual(validate_membership_datetime("۱۴۰۵/۶/۳۰"), "1405-06-30")
        self.assertEqual(validate_membership_datetime("2026-08-12 17:46:39"), "1405-05-21 17:46:39")
        self.assertEqual(validate_membership_datetime("1399/12/30"), "1399-12-30")

    def test_rejects_invalid_dates_including_non_leap_esfand(self):
        for text in ["1400/12/30", "1405/7/31", "2026/2/29", "1405/6/0", "1405/6/30 09:60", "garbage"]:
            with self.subTest(text=text), self.assertRaises(ValueError):
                validate_membership_datetime(text)
