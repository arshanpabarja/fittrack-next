from app.domain.errors import ValidationError


class AuthService:
    def __init__(self, repository):
        self.repository = repository

    def login(self, username, password):
        username = username.strip()
        if not username or not password:
            raise ValidationError("نام کاربری و رمز عبور را وارد کنید.")
        if not self.repository.verify(username, password):
            raise ValidationError("نام کاربری یا رمز عبور صحیح نیست.")
        return username

