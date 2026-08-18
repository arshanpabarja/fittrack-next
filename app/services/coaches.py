import re

from app.domain.errors import ValidationError


DIGITS = str.maketrans("۰۱۲۳۴۵۶۷۸۹٠١٢٣٤٥٦٧٨٩", "01234567890123456789")


class CoachesService:
    def __init__(self, api):
        self.api = api

    def load(self):
        return self.api.list_plans(), self.api.list_coaches()

    def save_coach(self, values, coach_id=None):
        mobile = re.sub(r"\s+", "", str(values.get("mobile", "")).translate(DIGITS))
        password = str(values.get("password", ""))
        plan_ids = values.get("plan_ids") or []
        if not re.fullmatch(r"09\d{9}", mobile):
            raise ValidationError("شماره موبایل باید ۱۱ رقم و با ۰۹ شروع شود.")
        if coach_id is None and not password:
            raise ValidationError("برای حساب جدید، رمز عبور الزامی است.")
        if password and len(password) < 8:
            raise ValidationError("رمز عبور باید حداقل ۸ کاراکتر باشد.")
        if not plan_ids:
            raise ValidationError("حداقل یک پلن مجاز انتخاب کنید.")
        return self.api.save_coach(
            mobile=mobile,
            password=password,
            plan_ids=plan_ids,
            coach_id=coach_id,
        )
