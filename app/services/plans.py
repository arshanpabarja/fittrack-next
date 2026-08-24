import json
import re
from pathlib import Path

from app.domain.errors import ValidationError


GENDER_TO_LOCAL = {"male": "مرد", "female": "زن", "all": "همه"}


class PlansService:
    def __init__(self, api, local_path):
        self.api = api
        self.local_path = Path(local_path)

    def load(self):
        return self.api.list_admin_plans()

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
        gender = str(values.get("gender", "all"))
        if gender not in GENDER_TO_LOCAL:
            raise ValidationError("جنسیت پلن معتبر نیست.")
        saved = self.api.save_plan(
            {
                "name": name,
                "price": price,
                "sessions_per_month": sessions,
                "gender": gender,
                "is_active": bool(values.get("is_active", True)),
            },
            plan_id,
        )
        plans = self.api.list_admin_plans()
        self._sync_local(plans)
        return saved

    def _sync_local(self, plans):
        existing = {}
        try:
            existing = json.loads(self.local_path.read_text(encoding="utf-8"))
        except (OSError, ValueError, TypeError):
            pass
        payload = {"مرد": [], "زن": [], "همه": []}
        for plan in plans:
            if not plan.is_active:
                continue
            payload[GENDER_TO_LOCAL.get(plan.gender, "همه")].append({
                "name": plan.name,
                "price": f"{plan.price:,} تومان",
            })
        if "single_session_price" in existing:
            payload["single_session_price"] = existing["single_session_price"]
        self.local_path.parent.mkdir(parents=True, exist_ok=True)
        self.local_path.write_text(
            json.dumps(payload, ensure_ascii=False, indent=4),
            encoding="utf-8",
        )
