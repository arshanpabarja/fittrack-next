import sqlite3
from datetime import datetime

from app.data.sqlite import SqliteDatabase
from app.domain.models import DashboardStats


class DashboardService:
    def __init__(self, members_path, attendance_path, single_session_path, current_attendance=None):
        self.members = SqliteDatabase(members_path)
        self.attendance = SqliteDatabase(attendance_path)
        self.single_sessions = SqliteDatabase(single_session_path)
        self.current_attendance = current_attendance

    @staticmethod
    def _scalar(database, query, parameters=(), budget_ms=1500):
        try:
            with database.connect(readonly=True, max_query_ms=budget_ms) as connection:
                row = connection.execute(query, parameters).fetchone()
                return int(row[0] or 0) if row else 0
        except (sqlite3.Error, OSError, ValueError):
            return None

    @staticmethod
    def _sum(left, right):
        return None if left is None or right is None else left + right

    def load(self):
        today = datetime.now().strftime("%Y-%m-%d") + "%"
        members = self._scalar(self.members, "SELECT COUNT(*) FROM users")
        if self.current_attendance is not None:
            inside, today_entries = self.current_attendance.dashboard_counts(today)
        else:
            inside_regular = self._scalar(
                self.attendance,
                "SELECT COUNT(*) FROM users WHERE checkout_time = 'Null'",
            )
            inside_guest = self._scalar(
                self.single_sessions,
                "SELECT COUNT(*) FROM users WHERE checkout_time = 'Null'",
            )
            today_regular = self._scalar(
                self.attendance,
                "SELECT COUNT(*) FROM users WHERE checkin_time LIKE ?",
                (today,),
            )
            today_guest = self._scalar(
                self.single_sessions,
                "SELECT COUNT(*) FROM users WHERE checkin_time LIKE ?",
                (today,),
            )
            inside = self._sum(inside_regular, inside_guest)
            today_entries = self._sum(today_regular, today_guest)
        return DashboardStats(
            members=members,
            inside=inside,
            today_entries=today_entries,
        )
