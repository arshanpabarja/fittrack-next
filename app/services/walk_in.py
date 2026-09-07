import json
import re
from pathlib import Path

from app.domain.errors import ValidationError
from app.domain.models import SignupPlan, WalkInSignupResult


DIGITS = str.maketrans("۰۱۲۳۴۵۶۷۸۹٠١٢٣٤٥٦٧٨٩", "01234567890123456789")


def _number(value):
    normalized = str(value or "0").translate(DIGITS)
    digits = re.sub(r"[^0-9]", "", normalized)
    return int(digits or 0)


class WalkInSignupService:
    def __init__(self, plans_path, members_repository, pos_terminal):
        self.plans_path = Path(plans_path)
        self.members = members_repository
        self.pos = pos_terminal

    def list_plans(self):
        try:
            payload = json.loads(self.plans_path.read_text(encoding="utf-8"))
        except (OSError, ValueError, TypeError) as exc:
            raise ValidationError("فهرست پلن‌های ثبت‌نام حضوری قابل خواندن نیست.") from exc
        plans = []
        index = 1
        for gender, items in payload.items():
            if not isinstance(items, list):
                continue
            for item in items:
                if not bool(item.get("is_active", True)):
                    continue
                name = str(item.get("name", "")).strip()
                if not name:
                    continue
                plans.append(SignupPlan(index, name, _number(item.get("price")), gender))
                index += 1
        return tuple(plans)

    def validate_profile(self, values):
        cleaned = dict(values)
        full_name = re.sub(r"\s+", " ", str(values.get("full_name", ""))).strip()
        parts = full_name.split(" ", 1)
        if len(parts) != 2 or len(parts[0]) < 2 or len(parts[1]) < 2:
            raise ValidationError("نام و نام خانوادگی را کامل وارد کنید.")
        mobile = re.sub(r"\s+", "", str(values.get("mobile", "")).translate(DIGITS))
        national_id = re.sub(r"\s+", "", str(values.get("national_id", "")).translate(DIGITS))
        address = re.sub(r"\s+", " ", str(values.get("address", ""))).strip()
        if not re.fullmatch(r"09\d{9}", mobile):
            raise ValidationError("شماره موبایل باید ۱۱ رقم و با ۰۹ شروع شود.")
        if not re.fullmatch(r"\d{10}", national_id):
            raise ValidationError("کد ملی باید دقیقاً ۱۰ رقم باشد.")
        if len(address) < 8:
            raise ValidationError("آدرس کامل محل سکونت را وارد کنید.")
        if self.members.find_id_by_mobile(mobile):
            raise ValidationError("عضوی با این شماره موبایل قبلاً ثبت شده است.")
        if self.members.find_id_by_national_id(national_id):
            raise ValidationError("عضوی با این کد ملی قبلاً ثبت شده است.")
        cleaned.update({
            "first_name": parts[0],
            "last_name": parts[1],
            "mobile": mobile,
            "national_id": national_id,
            "address": address,
            "father_name": str(values.get("father_name", "")).strip(),
            "certificate_no": str(values.get("certificate_no", "")).strip().translate(DIGITS),
            "gender": str(values.get("gender", "مرد")),
            "age": values.get("age"),
        })
        return cleaned

    def register(self, profile, plan, embedding, face_image):
        if not embedding or not face_image:
            raise ValidationError("چهره عضو هنوز ثبت نشده است.")
        cleaned = self.validate_profile(profile)
        receipt = self.pos.charge(plan.price)
        if not receipt.success:
            raise ValidationError(receipt.message)
        cleaned["plan"] = plan.name
        member_id = self.members.create_walk_in(
            cleaned,
            embedding,
            face_image,
            receipt.amount,
        )
        return WalkInSignupResult(
            member_id=member_id,
            full_name=f"{cleaned['first_name']} {cleaned['last_name']}",
            plan=plan.name,
            paid_amount=receipt.amount,
            payment_reference=receipt.reference,
        )
