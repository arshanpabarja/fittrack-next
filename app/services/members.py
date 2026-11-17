import logging
import re

from app.domain.dates import jalali_now, normalize_membership_datetime, validate_membership_datetime
from app.domain.errors import ValidationError
from app.domain.membership import grace_sessions, session_allowance
from app.domain.models import RenewalResult


DIGITS = str.maketrans("۰۱۲۳۴۵۶۷۸۹٠١٢٣٤٥٦٧٨٩", "01234567890123456789")


class MemberService:
    def __init__(self, repository, membership_repository=None, pos_terminal=None, api=None, audit=None):
        self.repository = repository
        self.membership_repository = membership_repository
        self.pos_terminal = pos_terminal
        self.api = api
        self.audit = audit

    def list_members(self, search="", page=1, page_size=40):
        return self.repository.list_page(search=search, page=page, page_size=page_size)

    def get_member(self, member_id):
        return self.repository.get(member_id)

    def update_member(self, member_id, values):
        before = self.repository.get(member_id) if self.audit else None
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
        cleaned.pop("used_sessions", None)
        if "signup_time" in cleaned:
            try:
                cleaned["signup_time"] = validate_membership_datetime(cleaned["signup_time"])
            except (ValueError, OverflowError) as exc:
                raise ValidationError("تاریخ ثبت‌نام معتبر نیست؛ مانند ۱۴۰۵/۰۶/۳۰ وارد کنید. ساعت اختیاری است.") from exc
        if "remaining_sessions" in cleaned:
            current = self.repository.get(member_id)
            allowance = session_allowance(cleaned.get("plan", current.plan))
            if allowance is None:
                raise ValidationError("برای تغییر جلسات باقی‌مانده، تعداد جلسات را در نام پلن مشخص کنید.")
            text = str(cleaned.pop("remaining_sessions")).strip().translate(DIGITS)
            if not re.fullmatch(r"-?\d+", text):
                raise ValidationError("جلسات باقی‌مانده باید عدد صحیح باشد.")
            remaining = int(text)
            if not -1_000_000 <= remaining <= allowance:
                raise ValidationError(f"جلسات باقی‌مانده نمی‌تواند بیشتر از {allowance} جلسهٔ پلن باشد.")
            cleaned["used_sessions"] = allowance - remaining
        updated = self.repository.update(member_id, cleaned)
        if "used_sessions" in cleaned and updated.remaining_sessions >= 0 and self.membership_repository:
            self.membership_repository.clear_grace(member_id)
        if self.audit:
            self.audit.record(
                "member_update",
                entity_type="member",
                entity_id=member_id,
                summary=f"ویرایش اطلاعات {updated.full_name}",
                before=before,
                after=updated,
            )
        return updated

    def delete_member(self, member_id):
        before = self.repository.get(member_id) if self.audit else None
        deleted = self.repository.delete(member_id)
        if self.audit:
            self.audit.record(
                "member_delete",
                entity_type="member",
                entity_id=member_id,
                summary=f"حذف عضو {before.full_name}",
                before=before,
            )
        return deleted

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
        now = jalali_now()
        grace_started_at = self.membership_repository.grace_started_at(member.id)
        membership_started_at = (
            normalize_membership_datetime(grace_started_at)
            if carried and grace_started_at
            else now
        )
        transaction_id = self.membership_repository.prepare_renewal(
            member_id=member.id,
            previous_plan=member.plan,
            new_plan=plan,
            carried_sessions=carried,
            membership_started_at=membership_started_at,
            requested_amount=amount,
        )
        try:
            receipt = self.pos_terminal.charge(amount)
        except Exception as exc:
            # The POS outcome is unknown. Keep payment_pending for manual review;
            # retrying the charge automatically could debit the card twice.
            try:
                self.membership_repository.record_pending_error(transaction_id, exc)
            except Exception:
                logging.getLogger(__name__).exception(
                    "Could not record uncertain POS outcome: %s", transaction_id
                )
            raise
        if not receipt.success:
            self.membership_repository.mark_payment_failed(
                transaction_id, receipt.message
            )
            raise ValidationError(receipt.message)
        self.membership_repository.record_emergency_receipt(
            transaction_id,
            paid_amount=receipt.amount,
            payment_reference=receipt.reference,
        )
        try:
            self.membership_repository.mark_payment_approved(
                transaction_id,
                paid_amount=receipt.amount,
                payment_reference=receipt.reference,
            )
        except Exception as exc:
            logging.getLogger(__name__).exception(
                "POS receipt saved to emergency journal: %s", transaction_id
            )
            raise ValidationError(
                "پرداخت تأیید شد و رسید اضطراری ذخیره شد، اما تمدید هنوز کامل نیست. "
                "پرداخت را دوباره انجام ندهید؛ از بخش پرداخت‌های ناقص بازیابی کنید."
            ) from exc
        self.membership_repository.clear_emergency_receipt(transaction_id)
        try:
            renewed = self.repository.renew_membership(
                member.id,
                plan=plan,
                carried_sessions=carried,
                signup_time=membership_started_at,
                paid_amount=receipt.amount,
            )
            self.membership_repository.mark_member_updated(transaction_id)
            self.membership_repository.complete_renewal(
                member_id=member.id,
                previous_plan=member.plan,
                new_plan=plan,
                carried_sessions=carried,
                membership_started_at=membership_started_at,
                paid_amount=receipt.amount,
                payment_reference=receipt.reference,
                transaction_id=transaction_id,
            )
        except Exception as exc:
            try:
                self.membership_repository.record_recovery_error(transaction_id, exc)
            except Exception:
                logging.getLogger(__name__).exception(
                    "Could not persist renewal recovery error: %s", transaction_id
                )
            logging.getLogger(__name__).exception(
                "Renewal payment approved but local completion is pending: %s",
                transaction_id,
            )
            raise ValidationError(
                "پرداخت تأیید شد، اما ثبت کامل تمدید به تعویق افتاد. "
                "پرداخت را دوباره انجام ندهید؛ برنامه در اجرای بعد آن را بازیابی می‌کند."
            ) from exc
        if self.audit:
            self.audit.record(
                "membership_renewal",
                entity_type="member",
                entity_id=member.id,
                summary=f"تمدید عضویت {renewed.full_name} به مبلغ {receipt.amount:,} تومان",
                before=member,
                after={
                    "plan": renewed.plan,
                    "paid_amount": receipt.amount,
                    "payment_reference": receipt.reference,
                    "membership_started_at": membership_started_at,
                    "transaction_id": transaction_id,
                },
            )
        return RenewalResult(
            member=renewed,
            carried_sessions=carried,
            membership_started_at=membership_started_at,
            paid_amount=receipt.amount,
            payment_reference=receipt.reference,
        )

    def recover_incomplete_renewals(self):
        """Complete locally approved payments without ever contacting POS again."""
        self.membership_repository.import_emergency_receipts()
        completed = 0
        for transaction in self.membership_repository.recoverable_renewals():
            try:
                if transaction["status"] == "payment_approved":
                    self.repository.renew_membership(
                        transaction["member_id"],
                        plan=transaction["new_plan"],
                        carried_sessions=transaction["carried_sessions"],
                        signup_time=transaction["membership_started_at"],
                        paid_amount=transaction["paid_amount"],
                    )
                    self.membership_repository.mark_member_updated(
                        transaction["transaction_id"]
                    )
                self.membership_repository.complete_renewal(
                    member_id=transaction["member_id"],
                    previous_plan=transaction["previous_plan"],
                    new_plan=transaction["new_plan"],
                    carried_sessions=transaction["carried_sessions"],
                    membership_started_at=transaction["membership_started_at"],
                    paid_amount=transaction["paid_amount"],
                    payment_reference=transaction["payment_reference"],
                    transaction_id=transaction["transaction_id"],
                )
                completed += 1
                if self.audit:
                    self.audit.record(
                        "renewal_recovery",
                        actor="سیستم",
                        entity_type="member",
                        entity_id=transaction["member_id"],
                        summary="تکمیل خودکار تمدید پرداخت‌شده",
                        after={"transaction_id": transaction["transaction_id"]},
                    )
            except Exception as exc:
                try:
                    self.membership_repository.record_recovery_error(
                        transaction["transaction_id"], exc
                    )
                except Exception:
                    logging.getLogger(__name__).exception(
                        "Could not persist recovery failure for %s",
                        transaction["transaction_id"],
                    )
                logging.getLogger(__name__).exception(
                    "Could not recover renewal transaction %s",
                    transaction["transaction_id"],
                )
        return completed

    def incomplete_renewals(self):
        if not self.membership_repository:
            return ()
        self.membership_repository.import_emergency_receipts()
        return tuple(self.membership_repository.incomplete_renewals())

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
