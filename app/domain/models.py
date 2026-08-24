from dataclasses import dataclass
from typing import Optional

from app.domain.membership import remaining_sessions, session_allowance


@dataclass(frozen=True)
class MemberSummary:
    id: int
    first_name: str
    last_name: str
    mobile: str
    national_id: str
    plan: str
    used_sessions: int
    debt: int
    signup_time: str

    @property
    def full_name(self):
        return f"{self.first_name} {self.last_name}".strip()

    @property
    def session_allowance(self):
        return session_allowance(self.plan)

    @property
    def remaining_sessions(self):
        return remaining_sessions(self.plan, self.used_sessions)

    @property
    def renewal_required(self):
        remaining = self.remaining_sessions
        return remaining is not None and remaining <= 0


@dataclass(frozen=True)
class MemberDetails(MemberSummary):
    father_name: str
    certificate_no: str
    address: str
    age: Optional[int]
    gender: str
    payment: int


@dataclass(frozen=True)
class MemberPage:
    items: tuple[MemberSummary, ...]
    page: int
    page_size: int
    has_next: bool


@dataclass(frozen=True)
class DashboardStats:
    members: Optional[int]
    inside: Optional[int]
    today_entries: Optional[int]


@dataclass
class AppSession:
    manager_authenticated: bool = False
    manager_username: str = ""


@dataclass(frozen=True)
class MembershipApplication:
    id: int
    full_name: str
    first_name: str
    last_name: str
    mobile: str
    national_id: str
    address: str
    plan: str
    plan_id: int
    gender: str
    price: int
    requested_at: str
    status: str


@dataclass(frozen=True)
class EnrollmentState:
    application_id: int
    status: str
    face_captured: bool
    paid_amount: int
    payment_reference: str
    legacy_member_id: Optional[int]
    last_error: str


@dataclass(frozen=True)
class PaymentReceipt:
    success: bool
    amount: int
    reference: str
    message: str


@dataclass(frozen=True)
class RecognizedMember:
    id: int
    full_name: str
    mobile: str
    plan: str
    used_sessions: int
    similarity: float
    signup_time: str = ""

    @property
    def session_allowance(self):
        return session_allowance(self.plan)

    @property
    def remaining_sessions(self):
        return remaining_sessions(self.plan, self.used_sessions)

    @property
    def renewal_required(self):
        remaining = self.remaining_sessions
        return remaining is not None and remaining <= 0


@dataclass(frozen=True)
class AttendanceResult:
    action: str
    member: RecognizedMember
    locker_id: Optional[int]
    occurred_at: str


@dataclass(frozen=True)
class RenewalResult:
    member: MemberDetails
    carried_sessions: int
    membership_started_at: str
    paid_amount: int
    payment_reference: str


@dataclass(frozen=True)
class SignupPlan:
    id: int
    name: str
    price: int
    gender: str = "all"
    sessions_per_month: int = 0
    is_active: bool = True


@dataclass(frozen=True)
class WalkInSignupResult:
    member_id: int
    full_name: str
    plan: str
    paid_amount: int
    payment_reference: str


@dataclass(frozen=True)
class CoachSummary:
    id: int
    full_name: str
    mobile: str
    specialty: str
    athlete_count: int


@dataclass(frozen=True)
class CoachProgram:
    id: int
    coach_id: int
    member_id: int
    member_name: str
    title: str
    exercises: str
    updated_at: str


@dataclass(frozen=True)
class CoachAccount:
    id: int
    mobile: str
    full_name: str
    specialty: str
    plan_ids: tuple[int, ...]
    plans: tuple[str, ...]
    profile_complete: bool


@dataclass(frozen=True)
class AttendanceRecord:
    id: int
    full_name: str
    mobile: str
    plan: str
    checked_in_at: str
    checked_out_at: str
    locker_id: Optional[int]


@dataclass(frozen=True)
class AttendancePageResult:
    items: tuple[AttendanceRecord, ...]
    page: int
    page_size: int
    has_next: bool
