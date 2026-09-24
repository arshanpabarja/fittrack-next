import json
from dataclasses import replace
from datetime import datetime

from app.domain.dates import normalize_membership_datetime
from app.domain.errors import FitTrackError
from app.domain.membership import remaining_sessions
from app.domain.models import AttendanceResult


class AttendanceService:
    def __init__(
        self,
        face_index,
        repository,
        members_repository,
        access_controller,
        membership_repository=None,
    ):
        self.face_index = face_index
        self.repository = repository
        self.members_repository = members_repository
        self.access_controller = access_controller
        self.membership_repository = membership_repository

    def refresh_faces(self):
        return self.face_index.refresh()

    def lookup_member(self, embedding):
        matched = self.face_index.match(embedding)
        return self.members_repository.get(matched.id)

    def check_in(self, embedding):
        member = self.face_index.match(embedding)
        current = self.members_repository.get(member.id)
        member = replace(
            member,
            full_name=current.full_name,
            mobile=current.mobile,
            plan=current.plan,
            used_sessions=current.used_sessions,
            signup_time=current.signup_time,
        )
        remaining_before = remaining_sessions(member.plan, member.used_sessions)
        if remaining_before is not None and remaining_before <= -5:
            raise FitTrackError(
                "پنج جلسه مهلت این عضو تمام شده است. ابتدا عضویت او را تمدید کنید."
            )
        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        _, locker_id = self.repository.check_in(member, timestamp)
        self._flush_outbox()
        member = replace(member, used_sessions=member.used_sessions + 1)
        if member.remaining_sessions is not None and member.remaining_sessions < 0:
            if self.membership_repository is not None:
                self.membership_repository.begin_grace(
                    member.id,
                    normalize_membership_datetime(timestamp),
                )
        self.access_controller.open_entry(locker_id)
        return AttendanceResult("check_in", member, locker_id, timestamp)

    def check_out(self, embedding):
        member = self.face_index.match(embedding)
        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        _, locker_id = self.repository.check_out(member.mobile, timestamp)
        self.access_controller.open_exit()
        return AttendanceResult("check_out", member, locker_id, timestamp)

    def summary(self):
        return self.repository.summary()

    def auto_checkout(self):
        return self.repository.auto_checkout(minutes=60)

    def _flush_outbox(self):
        for event in self.repository.pending_outbox():
            try:
                payload = json.loads(event["payload_json"])
                if event["event_type"] == "increment_session":
                    self.members_repository.increment_used_sessions(payload["member_id"])
                self.repository.mark_outbox_processed(event["id"])
            except Exception as exc:
                self.repository.mark_outbox_error(event["id"], exc)
