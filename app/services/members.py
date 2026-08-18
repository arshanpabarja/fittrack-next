import re

from app.domain.dates import jalali_now, normalize_membership_datetime
from app.domain.errors import ValidationError
from app.domain.membership import grace_sessions, session_allowance
from app.domain.models import RenewalResult


DIGITS = str.maketrans("۰۱۲۳۴۵۶۷۸۹٠١٢٣٤٥٦٧٨٩", "01234567890123456789")


class MemberService:
    def __init__(self, repository, membership_repository=None, pos_terminal=None, api=None):
        self.repository = repository
        self.membership_repository = membership_repository
        self.pos_terminal = pos_terminal
        self.api = api

    def list_members(self, search="", page=1, page_size=40):
        return self.repository.list_page(search=search, page=page, page_size=page_size)

    def get_member(self, member_id):
        return self.repository.get(member_id)

    def update_member(self, member_id, values):
        cleaned = dict(values)
        for key in ("mobile", "national_id"):
            cleaned[key] = re.sub(r"\s+", "", str(cleaned.get(key, "")).translate(DIGITS))
        if not cleaned.get("first_name", "").strip() or not cleaned.get("last_name", "").strip():
            raise ValidationError("نام و نام خانوادگی الزامی است.")
        if not re.fullmatch(r"09\d{9}", cleaned["mobile"]):
            raise ValidationError("شماره موبایل باید ۱۱ رقم و با ۰۹ شروع شود.")
        national_id = cleaned.get("national_id", "")
        if national_id and not re.fullmatch(r"\d{10}", national_id):
            raise ValidationError("کد ملی باید ۱۰ رقم باشد.")
        cleaned["first_name"] = cleaned["first_name"].strip()
        cleaned["last_name"] = cleaned["last_name"].strip()
        return self.repository.update(member_id, cleaned)

    def delete_member(self, member_id):
        return self.repository.delete(member_id)

    def renew_member(self, member_id, plan, amount):
        if self.membership_repository is None or self.pos_terminal is None:
            raise ValidationError("سرویس تمدید عضویت پیکربندی نشده است.")
        member = self.repository.get(member_id)
        plan = str(plan or "").strip()
        allowance = session_allowance(plan)
        if allowance is None:
            raise ValidationError("نام پلن باید شامل تعداد جلسات باشد؛ مثلاً «بدنسازی ۱۲ جلسه در ماه».")
        carried = grace_sessions(member.plan, member.used_sessions)
        if carried > 5:
            carried = 5
        if allowance <= carried:
            raise ValidationError(
                f"این پلن باید بیشتر از {carried} جلسه داشته باشد تا جلسات مهلت از آن کسر شود."
            )
        amount = max(0, int(amount or 0))
        receipt = self.pos_terminal.charge(amount)
        if not receipt.success:
            raise ValidationError(receipt.message)
        now = jalali_now()
        grace_started_at = self.membership_repository.grace_started_at(member.id)
        membership_started_at = (
            normalize_membership_datetime(grace_started_at)
            if carried and grace_started_at
            else now
        )
        renewed = self.repository.renew_membership(
            member.id,
            plan=plan,
            carried_sessions=carried,
            signup_time=membership_started_at,
            paid_amount=receipt.amount,
        )
        self.membership_repository.complete_renewal(
            member_id=member.id,
            previous_plan=member.plan,
            new_plan=plan,
            carried_sessions=carried,
            membership_started_at=membership_started_at,
            paid_amount=receipt.amount,
            payment_reference=receipt.reference,
        )
        return RenewalResult(
            member=renewed,
            carried_sessions=carried,
            membership_started_at=membership_started_at,
            paid_amount=receipt.amount,
            payment_reference=receipt.reference,
        )

    def reset_site_password(self, member_id, password, confirmation):
        if self.api is None:
            raise ValidationError("ارتباط تغییر رمز سایت پیکربندی نشده است.")
        password = str(password or "")
        if password != str(confirmation or ""):
            raise ValidationError("رمز جدید و تکرار آن یکسان نیست.")
        if len(password) < 8:
            raise ValidationError("رمز جدید باید حداقل ۸ کاراکتر باشد.")
        self.repository.get(member_id)
        return self.api.reset_member_password(member_id, password)
