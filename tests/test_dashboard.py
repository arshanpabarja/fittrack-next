import sqlite3
import tempfile
import unittest
from contextlib import closing
from pathlib import Path

from app.services.dashboard import DashboardService


class DashboardServiceTests(unittest.TestCase):
    def test_dashboard_combines_regular_and_guest_attendance(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            members = root / "members.db"
            attendance = root / "attendance.db"
            guests = root / "guests.db"
            with closing(sqlite3.connect(members)) as connection:
                connection.execute("CREATE TABLE users (id INTEGER, debt INTEGER)")
                connection.executemany("INSERT INTO users VALUES (?, ?)", [(1, 0), (2, 100)])
                connection.commit()
            for path in (attendance, guests):
                with closing(sqlite3.connect(path)) as connection:
                    connection.execute("CREATE TABLE users (checkin_time TEXT, checkout_time TEXT)")
                    connection.execute(
                        "INSERT INTO users VALUES (date('now') || ' 10:00:00', 'Null')"
                    )
                    connection.commit()
            stats = DashboardService(members, attendance, guests).load()
            self.assertEqual(stats.members, 2)
            self.assertEqual(stats.inside, 2)
            self.assertEqual(stats.today_entries, 2)


if __name__ == "__main__":
    unittest.main()
