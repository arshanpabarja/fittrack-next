from app.domain.errors import ValidationError


class AuthService:
    def __init__(self, repository, audit=None):
        self.repository = repository
        self.audit = audit

    def login(self, username, password):
        username = username.strip()
        if not username or not password:
            raise ValidationError("نام کاربری و رمز عبور را وارد کنید.")
        if not self.repository.verify(username, password):
            if self.audit:
                self.audit.record(
                    "manager_login_failed",
                    actor=username or "نامشخص",
                    summary="تلاش ناموفق برای ورود به بخش مدیریت",
                    success=False,
                    error="نام کاربری یا رمز عبور صحیح نیست.",
                )
            raise ValidationError("نام کاربری یا رمز عبور صحیح نیست.")
        if self.audit:
            self.audit.record(
                "manager_login",
                actor=username,
                summary="ورود موفق به بخش مدیریت",
            )
        return username

