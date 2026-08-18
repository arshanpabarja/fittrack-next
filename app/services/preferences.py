from app.domain.errors import ValidationError


DEFAULTS = {
    "api_url": "http://192.168.100.95:8000",
    "camera_indices": "0,1,2",
    "face_threshold": "0.50",
    "pos_mode": "fake",
    "locker_count": "72",
}


class PreferencesService:
    def __init__(self, repository):
        self.repository = repository

    def load(self):
        return {**DEFAULTS, **self.repository.all()}

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
        cleaned = {
            "api_url": api_url,
            "camera_indices": ",".join(map(str, indices)),
            "face_threshold": f"{threshold:.2f}",
            "pos_mode": "fake",
            "locker_count": "72",
        }
        return self.repository.save(cleaned)

