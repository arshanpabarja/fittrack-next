from django.contrib.auth.base_user import BaseUserManager
from django.contrib.auth.models import AbstractUser
from django.db import models
from django.utils import timezone


class UserManager(BaseUserManager):
    use_in_migrations = True

    def create_user(self, mobile, password=None, **extra_fields):
        if not mobile:
            raise ValueError("شماره موبایل الزامی است.")
        user = self.model(mobile=mobile, **extra_fields)
        user.set_password(password)
        user.save(using=self._db)
        return user

    def create_superuser(self, mobile, password=None, **extra_fields):
        extra_fields.setdefault("is_staff", True)
        extra_fields.setdefault("is_superuser", True)
        extra_fields.setdefault("role", User.Role.ADMIN)
        extra_fields.setdefault("status", User.Status.ACTIVE)
        return self.create_user(mobile, password, **extra_fields)


class User(AbstractUser):
    class Role(models.TextChoices):
        MEMBER = "member", "عضو"
        COACH = "coach", "مربی"
        STAFF = "staff", "پذیرش"
        ADMIN = "admin", "مدیر"

    class Status(models.TextChoices):
        PENDING = "pending", "در انتظار مراجعه"
        ACTIVE = "active", "فعال"
        SUSPENDED = "suspended", "تعلیق‌شده"

    username = None
    mobile = models.CharField(max_length=11, unique=True, db_index=True)
    national_id = models.CharField(max_length=10, unique=True, null=True, blank=True)
    address = models.TextField(blank=True)
    role = models.CharField(max_length=12, choices=Role.choices, default=Role.MEMBER)
    status = models.CharField(max_length=12, choices=Status.choices, default=Status.PENDING, db_index=True)

    USERNAME_FIELD = "mobile"
    REQUIRED_FIELDS = []
    objects = UserManager()

    def __str__(self):
        return f"{self.get_full_name() or self.mobile} ({self.mobile})"


class Plan(models.Model):
    class Gender(models.TextChoices):
        ALL = "all", "همه"
        MALE = "male", "مرد"
        FEMALE = "female", "زن"

    name = models.CharField(max_length=160, unique=True)
    gender = models.CharField(max_length=8, choices=Gender.choices, default=Gender.ALL)
    price = models.PositiveBigIntegerField(default=0)
    sessions_per_month = models.PositiveSmallIntegerField(default=0)
    is_active = models.BooleanField(default=True, db_index=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["price", "name"]

    def __str__(self):
        return self.name


class MembershipApplication(models.Model):
    class Status(models.TextChoices):
        PENDING = "pending", "در انتظار مراجعه"
        ACTIVE = "active", "فعال"
        REJECTED = "rejected", "ردشده"
        CANCELLED = "cancelled", "لغوشده"

    user = models.OneToOneField(User, on_delete=models.CASCADE, related_name="membership_application")
    plan = models.ForeignKey(Plan, on_delete=models.PROTECT, related_name="applications")
    status = models.CharField(max_length=12, choices=Status.choices, default=Status.PENDING, db_index=True)
    legacy_member_id = models.PositiveIntegerField(null=True, blank=True, unique=True)
    requested_at = models.DateTimeField(auto_now_add=True)
    activated_at = models.DateTimeField(null=True, blank=True)
    paid_amount = models.PositiveBigIntegerField(default=0)
    face_registered = models.BooleanField(default=False)
    notes = models.TextField(blank=True)

    class Meta:
        indexes = [models.Index(fields=["status", "requested_at"], name="idx_application_status_date")]

    def activate(self, legacy_member_id, paid_amount):
        self.status = self.Status.ACTIVE
        self.legacy_member_id = legacy_member_id
        self.paid_amount = max(0, int(paid_amount))
        self.face_registered = True
        self.activated_at = timezone.now()
        self.user.status = User.Status.ACTIVE
        self.user.save(update_fields=["status"])
        self.save(update_fields=["status", "legacy_member_id", "paid_amount", "face_registered", "activated_at"])


class CoachProfile(models.Model):
    user = models.OneToOneField(
        User,
        on_delete=models.CASCADE,
        related_name="coach_profile",
        limit_choices_to={"role": User.Role.COACH},
    )
    specialty = models.CharField(max_length=160, blank=True)
    bio = models.TextField(blank=True)
    allowed_plans = models.ManyToManyField(Plan, related_name="coaches", blank=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return self.user.get_full_name().strip() or self.user.mobile


class WorkoutProgram(models.Model):
    coach = models.ForeignKey(
        User,
        on_delete=models.CASCADE,
        related_name="authored_workout_programs",
        limit_choices_to={"role": User.Role.COACH},
    )
    member = models.ForeignKey(
        User,
        on_delete=models.CASCADE,
        related_name="workout_programs",
        limit_choices_to={"role": User.Role.MEMBER},
    )
    title = models.CharField(max_length=180)
    exercises = models.TextField()
    duration_weeks = models.PositiveSmallIntegerField(default=4)
    schedule_json = models.JSONField(default=list, blank=True)
    updated_at = models.DateTimeField(auto_now=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-updated_at"]
        constraints = [
            models.UniqueConstraint(
                fields=["coach", "member"],
                name="uq_current_program_per_coach_member",
            )
        ]

    def __str__(self):
        return f"{self.title} — {self.member.get_full_name() or self.member.mobile}"


class LegacyMember(models.Model):
    id = models.AutoField(primary_key=True)
    first_name = models.TextField()
    last_name = models.TextField()
    father_name = models.TextField(null=True, blank=True)
    national_id = models.TextField(null=True, blank=True)
    certificate_no = models.TextField(null=True, blank=True)
    address = models.TextField(null=True, blank=True)
    mobile = models.TextField()
    age = models.IntegerField(null=True, blank=True)
    gender = models.TextField()
    plan = models.TextField()
    embedding = models.TextField(null=True, blank=True)
    face_image = models.BinaryField(null=True, blank=True)
    used_sessions = models.IntegerField(default=0)
    signup_time = models.TextField()
    debt = models.IntegerField(default=0)
    payment = models.IntegerField(default=0)

    class Meta:
        managed = False
        db_table = "users"

# Create your models here.
