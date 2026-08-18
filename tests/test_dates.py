import unittest
from datetime import datetime

from app.domain.dates import (
    gregorian_to_jalali,
    jalali_now,
    normalize_membership_datetime,
)


class MembershipDateTests(unittest.TestCase):
    def test_known_gregorian_dates_convert_to_jalali(self):
        self.assertEqual(gregorian_to_jalali(2024, 3, 20), (1403, 1, 1))
        self.assertEqual(gregorian_to_jalali(2026, 8, 18), (1405, 5, 27))

    def test_new_membership_date_is_always_jalali(self):
        self.assertEqual(
            jalali_now(datetime(2026, 8, 18, 22, 15, 7)),
            "1405-05-27 22:15:07",
        )

    def test_existing_membership_dates_are_normalized(self):
        self.assertEqual(
            normalize_membership_datetime("2026-08-12 17:46:39"),
            "1405-05-21 17:46:39",
        )
        self.assertEqual(
            normalize_membership_datetime("1404-07-26_ 08:01:07"),
            "1404-07-26 08:01:07",
        )
        self.assertEqual(
            normalize_membership_datetime("1405_01_15"),
            "1405-01-15",
        )


if __name__ == "__main__":
    unittest.main()
