import json
import re
from pathlib import Path

from app.domain.errors import RecordNotFound, ValidationError
from app.domain.membership import session_allowance
from app.domain.models import SignupPlan


GENDER_TO_LOCAL = {"male": "مرد", "female": "زن", "all": "همه"}
LOCAL_TO_GENDER = {value: key for key, value in GENDER_TO_LOCAL.items()}
DIGITS = str.maketrans("۰۱۲۳۴۵۶۷۸۹٠١٢٣٤٥٦٧٨٩", "01234567890123456789")


def _number(value):
    normalized = str(value or "0").translate(DIGITS)
    return int(re.sub(r"[^0-9]", "", normalized) or 0)


class PlansService:
    """Manage the live, local Life Box plan catalog without requiring Django."""

    def __init__(self, api, local_path):
        self.api = api
        self.local_path = Path(local_path)

    def _read_local(self):
        try:
            payload = json.loads(self.local_path.read_text(encoding="utf-8-sig"))
        except (OSError, ValueError, TypeError) as exc:
            raise ValidationError("فهرست پلن‌های باشگاه قابل خواندن نیست.") from exc
        if not isinstance(payload, dict):
            raise ValidationError("ساختار فایل پلن‌های باشگاه معتبر نیست.")
        return payload

    def load(self):
        payload = self._read_local()
        plans = []
        used_ids = set()
        next_id = 1
        for local_gender in ("مرد", "زن", "همه"):
            items = payload.get(local_gender, [])
            if not isinstance(items, list):
                continue
            for item in items:
                if not isinstance(item, dict):
                    continue
                name = re.sub(r"\s+", " ", str(item.get("name", ""))).strip()
                if not name:
                    continue
                try:
                    plan_id = int(item.get("id", 0))
                except (TypeError, ValueError):
                    plan_id = 0
                if plan_id <= 0 or plan_id in used_ids:
                    while next_id in used_ids:
                        next_id += 1
                    plan_id = next_id
                used_ids.add(plan_id)
                next_id = max(next_id, plan_id + 1)
                sessions = _number(item.get("sessions_per_month")) or session_allowance(name) or 0
                plans.append(SignupPlan(
                    id=plan_id,
                    name=name,
                    price=_number(item.get("price")),
                    gender=LOCAL_TO_GENDER[local_gender],
                    sessions_per_month=sessions,
                    is_active=bool(item.get("is_active", True)),
                ))
        return tuple(plans)

    def save(self, values, plan_id=None):
        name = re.sub(r"\s+", " ", str(values.get("name", ""))).strip()
        if len(name) < 3:
            raise ValidationError("نام پلن باید حداقل سه کاراکتر باشد.")
        try:
            price = int(values.get("price", 0))
            sessions = int(values.get("sessions_per_month", 0))
        except (TypeError, ValueError) as exc:
            raise ValidationError("مبلغ و تعداد جلسات باید عدد معتبر باشند.") from exc
        if price < 0:
            raise ValidationError("مبلغ پلن نمی‌تواند منفی باشد.")
        if not 1 <= sessions <= 60:
            raise ValidationError("تعداد جلسات باید بین ۱ تا ۶۰ باشد.")
        if session_allowance(name) != sessions:
            raise ValidationError(
                f"نام پلن باید در پایان شامل «{sessions} جلسه در ماه» باشد تا شمارش جلسات درست انجام شود."
            )
        gender = str(values.get("gender", "all"))
        if gender not in GENDER_TO_LOCAL:
            raise ValidationError("جنسیت پلن معتبر نیست.")

        plans = list(self.load())
        if plan_id is None:
            saved_id = max((plan.id for plan in plans), default=0) + 1
        else:
            saved_id = int(plan_id)
            if not any(plan.id == saved_id for plan in plans):
                raise RecordNotFound("پلن انتخاب‌شده در فهرست محلی پیدا نشد.")
        saved = SignupPlan(
            id=saved_id,
            name=name,
            price=price,
            gender=gender,
            sessions_per_month=sessions,
            is_active=bool(values.get("is_active", True)),
        )
        plans = [saved if plan.id == saved_id else plan for plan in plans]
        if plan_id is None:
            plans.append(saved)
        self._write_local(plans)
        return saved

    def _write_local(self, plans):
        existing = self._read_local()
        payload = {
            key: value
            for key, value in existing.items()
            if key not in LOCAL_TO_GENDER
        }
        for local_gender in ("مرد", "زن", "همه"):
            payload[local_gender] = []
        for plan in plans:
            payload[GENDER_TO_LOCAL[plan.gender]].append({
                "id": plan.id,
                "name": plan.name,
                "price": plan.price,
                "sessions_per_month": plan.sessions_per_month,
                "is_active": plan.is_active,
            })
        self.local_path.parent.mkdir(parents=True, exist_ok=True)
        temporary = self.local_path.with_suffix(self.local_path.suffix + ".tmp")
        temporary.write_text(
            json.dumps(payload, ensure_ascii=False, indent=4),
            encoding="utf-8",
        )
        temporary.replace(self.local_path)
