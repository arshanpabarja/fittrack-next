import os
from ipaddress import ip_address

from app.domain.errors import ValidationError


DEFAULTS = {
    "api_url": "http://192.168.100.95:8000",
    "camera_indices": "0,1,2",
    "face_threshold": "0.50",
    "pos_mode": "real",
    "pos_host": "192.168.100.54",
    "pos_port": "3030",
    "pos_timeout": "60",
    "locker_count": "72",
}


class PreferencesService:
    def __init__(self, repository):
        self.repository = repository

    def load(self):
        values = {**DEFAULTS, **self.repository.all()}
        if "FITTRACK_POS_MODE" in os.environ:
            values["pos_mode"] = os.environ["FITTRACK_POS_MODE"].strip().lower()
        return values

    def save(self, values):
        api_url = str(values.get("api_url", "")).strip().rstrip("/")
        if not api_url.startswith(("http://", "https://")):
            raise ValidationError("آدرس API باید با http:// یا https:// شروع شود.")
        try:
            indices = [int(item.strip()) for item in str(values.get("camera_indices", "")).split(",")]
            if not indices or any(item < 0 or item > 20 for item in indices):
                raise ValueError
        except ValueError as exc:
            raise ValidationError("شماره دوربین‌ها را مانند 0,1,2 وارد کنید.") from exc
        try:
            threshold = float(values.get("face_threshold", ""))
        except ValueError as exc:
            raise ValidationError("آستانه چهره عدد معتبری نیست.") from exc
        if not 0.2 <= threshold <= 0.95:
            raise ValidationError("آستانه چهره باید بین 0.20 و 0.95 باشد.")
        current = self.load()
        mode = str(values.get("pos_mode", current["pos_mode"])).strip().lower()
        if mode not in {"fake", "real"}:
            raise ValidationError("حالت کارتخوان باید real یا fake باشد.")
        host = str(values.get("pos_host", current["pos_host"])).strip()
        try:
            ip_address(host)
            port = int(values.get("pos_port", current["pos_port"]))
            timeout = int(values.get("pos_timeout", current["pos_timeout"]))
            if not 1 <= port <= 65535 or not 5 <= timeout <= 300:
                raise ValueError
        except (ValueError, TypeError) as exc:
            raise ValidationError("IP کارتخوان، پورت ۱ تا ۶۵۵۳۵ و زمان انتظار ۵ تا ۳۰۰ ثانیه را وارد کنید.") from exc
        cleaned = {
            "api_url": api_url,
            "camera_indices": ",".join(map(str, indices)),
            "face_threshold": f"{threshold:.2f}",
            "pos_mode": mode,
            "pos_host": host,
            "pos_port": str(port),
            "pos_timeout": str(timeout),
            "locker_count": "72",
        }
        return self.repository.save(cleaned)
