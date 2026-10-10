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
        extra_fields.setdefault("role", User.Role.OWNER)
        extra_fields.setdefault("status", User.Status.ACTIVE)
        return self.create_user(mobile, password, **extra_fields)


class User(AbstractUser):
    class Role(models.TextChoices):
        MEMBER = "member", "عضو"
        COACH = "coach", "مربی"
        STAFF = "staff", "پذیرش"
        ADMIN = "admin", "ادمین"
        OWNER = "owner", "مالک"

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

    # Desktop plan IDs identify plans; display names may repeat across catalogs.
    name = models.CharField(max_length=160)
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


class SignupOTP(models.Model):
    mobile = models.CharField(max_length=11, unique=True, db_index=True)
    code_digest = models.CharField(max_length=64)
    expires_at = models.DateTimeField()
    last_sent_at = models.DateTimeField()
    window_started_at = models.DateTimeField()
    send_count = models.PositiveSmallIntegerField(default=1)
    failed_attempts = models.PositiveSmallIntegerField(default=0)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return self.mobile


class PasswordResetChallenge(models.Model):
    mobile = models.CharField(max_length=11, unique=True)
    user = models.ForeignKey(User, null=True, blank=True, on_delete=models.CASCADE)
    code_digest = models.CharField(max_length=64, blank=True)
    token_digest = models.CharField(max_length=64, blank=True)
    password_digest = models.CharField(max_length=64, blank=True)
    expires_at = models.DateTimeField()
    last_sent_at = models.DateTimeField()
    window_started_at = models.DateTimeField()
    send_count = models.PositiveSmallIntegerField(default=0)
    failed_attempts = models.PositiveSmallIntegerField(default=0)


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
    main_goal = models.CharField(max_length=40, blank=True)
    start_date = models.DateField(null=True, blank=True)
    end_date = models.DateField(null=True, blank=True)
    coach_notes = models.TextField(blank=True)
    archived_at = models.DateTimeField(null=True, blank=True)
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


class TrainingProfile(models.Model):
    coach = models.ForeignKey(User, on_delete=models.CASCADE, related_name='client_training_profiles')
    member = models.ForeignKey(User, on_delete=models.CASCADE, related_name='training_profiles')
    main_goal = models.CharField(max_length=40, blank=True)
    experience = models.CharField(max_length=40, blank=True)
    frequency = models.PositiveSmallIntegerField(default=3)
    preferred_style = models.CharField(max_length=160, blank=True)
    limitations = models.TextField(blank=True)
    injuries = models.TextField(blank=True)
    notes = models.TextField(blank=True)
    reported_pain = models.BooleanField(default=False)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        constraints = [models.UniqueConstraint(fields=['coach', 'member'], name='unique_coach_training_profile')]


class ProgramRevision(models.Model):
    program = models.ForeignKey(WorkoutProgram, on_delete=models.CASCADE, related_name='revisions')
    snapshot = models.JSONField(default=dict)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-created_at', '-id']


class Assessment(models.Model):
    coach = models.ForeignKey(User, on_delete=models.CASCADE, related_name='client_assessments')
    member = models.ForeignKey(User, on_delete=models.CASCADE, related_name='assessments')
    measured_on = models.DateField(default=timezone.localdate)
    weight = models.DecimalField(max_digits=6, decimal_places=2, null=True, blank=True)
    height = models.DecimalField(max_digits=6, decimal_places=2, null=True, blank=True)
    body_fat = models.DecimalField(max_digits=5, decimal_places=2, null=True, blank=True)
    waist = models.DecimalField(max_digits=6, decimal_places=2, null=True, blank=True)
    chest = models.DecimalField(max_digits=6, decimal_places=2, null=True, blank=True)
    arms = models.DecimalField(max_digits=6, decimal_places=2, null=True, blank=True)
    thighs = models.DecimalField(max_digits=6, decimal_places=2, null=True, blank=True)
    bench_press = models.DecimalField(max_digits=6, decimal_places=2, null=True, blank=True)
    squat = models.DecimalField(max_digits=6, decimal_places=2, null=True, blank=True)
    deadlift = models.DecimalField(max_digits=6, decimal_places=2, null=True, blank=True)
    pull_ups = models.PositiveSmallIntegerField(null=True, blank=True)
    fitness_notes = models.TextField(blank=True)
    mobility_notes = models.TextField(blank=True)
    strength_notes = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-measured_on', '-id']


class TrainingSession(models.Model):
    class Status(models.TextChoices):
        SCHEDULED = 'scheduled', 'برنامه‌ریزی‌شده'
        IN_PROGRESS = 'in_progress', 'در حال تمرین'
        COMPLETED = 'completed', 'انجام‌شده'
        CANCELLED = 'cancelled', 'لغوشده'
        NO_SHOW = 'no_show', 'عدم حضور'

    coach = models.ForeignKey(User, on_delete=models.CASCADE, related_name='coached_sessions')
    member = models.ForeignKey(User, on_delete=models.CASCADE, related_name='training_sessions')
    program = models.ForeignKey(WorkoutProgram, on_delete=models.SET_NULL, null=True, blank=True)
    program_title = models.CharField(max_length=180, blank=True)
    training_day = models.CharField(max_length=160, blank=True)
    scheduled_at = models.DateTimeField(db_index=True)
    duration_minutes = models.PositiveSmallIntegerField(default=60)
    group_label = models.CharField(max_length=160, blank=True)
    exercises = models.JSONField(default=list, blank=True)
    status = models.CharField(max_length=16, choices=Status.choices, default=Status.SCHEDULED)
    notes = models.TextField(blank=True)
    completed_at = models.DateTimeField(null=True, blank=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['scheduled_at', 'id']


class CoachNote(models.Model):
    coach = models.ForeignKey(User, on_delete=models.CASCADE, related_name='private_coach_notes')
    member = models.ForeignKey(User, on_delete=models.CASCADE, related_name='coach_notes')
    session = models.ForeignKey(TrainingSession, on_delete=models.SET_NULL, null=True, blank=True)
    content = models.TextField()
    follow_up_on = models.DateField(null=True, blank=True)
    resolved = models.BooleanField(default=False)
    reported_pain = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-created_at', '-id']


class Exercise(models.Model):
    coach = models.ForeignKey(User, on_delete=models.CASCADE, null=True, blank=True, related_name='custom_exercises')
    name = models.CharField(max_length=160)
    muscle_group = models.CharField(max_length=24)
    equipment = models.CharField(max_length=160, blank=True)
    instructions = models.TextField(blank=True)
    common_mistakes = models.TextField(blank=True)
    media_url = models.URLField(blank=True)

    class Meta:
        ordering = ['muscle_group', 'name', 'id']


class LoginEvent(models.Model):
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name="login_events")
    occurred_at = models.DateTimeField(default=timezone.now, db_index=True)


class OwnerAudit(models.Model):
    actor = models.ForeignKey(User, on_delete=models.SET_NULL, null=True)
    action = models.CharField(max_length=160)
    occurred_at = models.DateTimeField(default=timezone.now, db_index=True)


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


class GymSyncCursor(models.Model):
    source = models.CharField(max_length=80, primary_key=True)
    sequence = models.PositiveBigIntegerField(default=0)
    digest = models.CharField(max_length=64, blank=True)
    updated_at = models.DateTimeField(auto_now=True)


class GymSyncRecord(models.Model):
    kind = models.CharField(max_length=16)
    local_id = models.PositiveBigIntegerField()
    data = models.JSONField(default=dict)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        constraints = [models.UniqueConstraint(fields=['kind', 'local_id'], name='unique_gym_sync_record')]


class GymRemoteCommand(models.Model):
    class Status(models.TextChoices):
        PENDING = 'pending', 'در انتظار دریافت باشگاه'
        APPLIED = 'applied', 'اعمال‌شده'
        FAILED = 'failed', 'ناموفق'

    kind = models.CharField(max_length=16)
    local_id = models.PositiveBigIntegerField()
    data = models.JSONField(default=dict)
    create = models.BooleanField(default=False)
    web_user = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True)
    selected_plan = models.ForeignKey(Plan, on_delete=models.SET_NULL, null=True, blank=True)
    status = models.CharField(max_length=12, choices=Status.choices, default=Status.PENDING, db_index=True)
    error = models.CharField(max_length=500, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    completed_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ['id']


class MemberWorkout(models.Model):
    """Member-entered results, separate from the coach's immutable prescription."""
    member = models.ForeignKey(User, on_delete=models.CASCADE, related_name='workout_logs')
    coach = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, related_name='member_workout_logs')
    program = models.ForeignKey(WorkoutProgram, on_delete=models.SET_NULL, null=True)
    program_title = models.CharField(max_length=180)
    training_day = models.CharField(max_length=160)
    day_index = models.PositiveSmallIntegerField(default=0)
    exercises = models.JSONField(default=list)
    personal_note = models.TextField(blank=True)
    started_at = models.DateTimeField(auto_now_add=True)
    finished_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ['-started_at', '-id']
        constraints = [models.UniqueConstraint(fields=['member'], condition=models.Q(finished_at__isnull=True), name='one_open_member_workout')]


class MemberRequest(models.Model):
    class Status(models.TextChoices):
        PENDING = 'pending', 'در انتظار بررسی'
        APPROVED = 'approved', 'تأییدشده'
        CLOSED = 'closed', 'بسته‌شده'

    member = models.ForeignKey(User, on_delete=models.CASCADE, related_name='support_requests')
    kind = models.CharField(max_length=40)
    message = models.TextField()
    status = models.CharField(max_length=12, choices=Status.choices, default=Status.PENDING)
    reply = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['-created_at', '-id']


class MemberPreferences(models.Model):
    member = models.OneToOneField(User, on_delete=models.CASCADE, related_name='member_preferences')
    notifications_enabled = models.BooleanField(default=True)
    read_notifications = models.JSONField(default=list)
