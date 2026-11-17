import logging
from dataclasses import asdict, is_dataclass
from threading import RLock


ACTION_LABELS = {
    "manager_login": "ورود مدیر",
    "manager_login_failed": "ورود ناموفق",
    "manager_logout": "خروج مدیر",
    "member_update": "ویرایش عضو",
    "member_delete": "حذف عضو",
    "membership_renewal": "تمدید عضویت",
    "plan_create": "ساخت پلن",
    "plan_update": "ویرایش پلن",
    "settings_update": "تغییر تنظیمات",
    "coach_create": "ساخت حساب مربی",
    "coach_update": "ویرایش حساب مربی",
    "desktop_update": "آپدیت برنامه",
    "renewal_recovery": "بازیابی تمدید",
}


SENSITIVE_FIELDS = {
    "password",
    "password_hash",
    "face_image",
    "embedding",
    "token",
    "api_token",
}


def safe_snapshot(value):
    if value is None:
        return {}
    if is_dataclass(value):
        value = asdict(value)
    elif not isinstance(value, dict):
        return {"value": str(value)}
    return {
        str(key): item
        for key, item in value.items()
        if str(key).lower() not in SENSITIVE_FIELDS
    }


class AuditService:
    def __init__(self, repository):
        self.repository = repository
        self._actor = ""
        self._lock = RLock()

    def set_actor(self, username=""):
        with self._lock:
            self._actor = str(username or "").strip()

    @property
    def actor(self):
        with self._lock:
            return self._actor or "اپراتور دستگاه"

    def record(self, action, *, actor=None, **details):
        try:
            details["before"] = safe_snapshot(details.get("before"))
            details["after"] = safe_snapshot(details.get("after"))
            return self.repository.append(
                actor=actor if actor is not None else self.actor,
                action=action,
                **details,
            )
        except Exception:
            # Auditing must never turn a successful club operation into a failure.
            logging.getLogger(__name__).exception("Could not append manager audit event")
            return None

    def list_activity(self, search="", action="", limit=500):
        return self.repository.list(search=search, action=action, limit=limit)

    def actions(self):
        return tuple(ACTION_LABELS.items())
