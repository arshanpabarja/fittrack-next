import hashlib

from django import forms
from django.contrib import admin
from django.contrib.auth.admin import UserAdmin
from django.utils import timezone
from app.core.update_security import validate_version, verify_release

from .models import (
    CoachProfile,
    DesktopDevice,
    DesktopLogEvent,
    DesktopRelease,
    DesktopUpdateAttempt,
    MembershipApplication,
    Plan,
    User,
    WorkoutProgram,
    MemberRequest,
)


@admin.register(User)
class LifeBoxUserAdmin(UserAdmin):
    ordering = ("-date_joined",)
    list_display = ("mobile", "first_name", "last_name", "role", "status", "is_staff")
    list_filter = ("role", "status", "is_staff")
    search_fields = ("mobile", "first_name", "last_name", "national_id")
    fieldsets = (
        (None, {"fields": ("mobile", "password")}),
        ("اطلاعات شخصی", {"fields": ("first_name", "last_name", "national_id", "address")}),
        ("دسترسی", {"fields": ("role", "status", "is_active", "is_staff", "is_superuser", "groups", "user_permissions")}),
        ("تاریخ‌ها", {"fields": ("last_login", "date_joined")}),
    )
    add_fieldsets = ((None, {"classes": ("wide",), "fields": ("mobile", "password1", "password2", "role", "status")}),)


@admin.register(Plan)
class PlanAdmin(admin.ModelAdmin):
    list_display = ("name", "gender", "price", "sessions_per_month", "is_active")
    list_filter = ("gender", "is_active")
    search_fields = ("name",)


@admin.register(CoachProfile)
class CoachProfileAdmin(admin.ModelAdmin):
    list_display = ("user", "specialty", "updated_at")
    filter_horizontal = ("allowed_plans",)
    search_fields = ("user__mobile", "user__first_name", "user__last_name", "specialty")


@admin.register(WorkoutProgram)
class WorkoutProgramAdmin(admin.ModelAdmin):
    list_display = ("title", "coach", "member", "updated_at")
    search_fields = ("title", "coach__mobile", "member__mobile")


@admin.register(MembershipApplication)
class MembershipApplicationAdmin(admin.ModelAdmin):
    list_display = ("user", "plan", "status", "requested_at", "activated_at", "legacy_member_id")
    list_filter = ("status", "plan")
    search_fields = ("user__mobile", "user__first_name", "user__last_name", "user__national_id")

@admin.register(MemberRequest)
class MemberRequestAdmin(admin.ModelAdmin):
    list_display = ('member', 'kind', 'status', 'created_at')
    list_filter = ('status', 'kind')
    search_fields = ('member__mobile', 'member__first_name', 'member__last_name', 'message')
    readonly_fields = ('member', 'kind', 'message', 'created_at', 'updated_at')
    fields = ('member', 'kind', 'message', 'status', 'reply', 'created_at', 'updated_at')

    def has_add_permission(self, request):
        return False


@admin.register(DesktopDevice)
class DesktopDeviceAdmin(admin.ModelAdmin):
    list_display = (
        'source', 'app_version', 'database_ok', 'pending_sync',
        'free_disk', 'last_seen_at',
    )
    list_filter = ('database_ok', 'app_version')
    search_fields = ('source', 'platform')
    readonly_fields = (
        'source', 'app_version', 'platform', 'state_size', 'free_disk',
        'database_ok', 'pending_sync', 'process_id', 'last_seen_at',
    )

    def has_add_permission(self, request):
        return False

    def has_delete_permission(self, request, obj=None):
        return False


@admin.register(DesktopLogEvent)
class DesktopLogEventAdmin(admin.ModelAdmin):
    list_display = ('occurred_at', 'device', 'level', 'logger', 'short_message')
    list_filter = ('level', 'device')
    search_fields = ('message', 'logger', 'device__source')
    readonly_fields = (
        'device', 'local_id', 'level', 'logger', 'message',
        'occurred_at', 'received_at',
    )

    @admin.display(description='پیام')
    def short_message(self, obj):
        return obj.message[:120]

    def has_add_permission(self, request):
        return False

    def has_delete_permission(self, request, obj=None):
        return False


@admin.register(DesktopRelease)
class DesktopReleaseAdmin(admin.ModelAdmin):
    list_display = ('version', 'package_size', 'is_published', 'published_at', 'created_at')
    list_filter = ('is_published',)
    search_fields = ('version', 'notes')
    readonly_fields = ('sha256', 'package_size', 'created_at', 'published_at')

    class ReleaseForm(forms.ModelForm):
        class Meta:
            model = DesktopRelease
            fields = '__all__'

        def clean(self):
            cleaned = super().clean()
            package = cleaned.get('package')
            version = cleaned.get('version')
            signature = cleaned.get('signature')
            if not package or not version:
                return cleaned
            digest = hashlib.sha256()
            size = 0
            package.seek(0)
            for chunk in package.chunks():
                digest.update(chunk)
                size += len(chunk)
            package.seek(0)
            self.instance.sha256 = digest.hexdigest()
            self.instance.package_size = size
            try:
                validate_version(version)
                if size <= 0 or size > 800 * 1024 * 1024:
                    raise ValueError("حجم فایل نسخه معتبر نیست.")
                if cleaned.get('is_published'):
                    verify_release(version, self.instance.sha256, size, signature)
            except ValueError as exc:
                raise forms.ValidationError(str(exc)) from exc
            return cleaned

    form = ReleaseForm

    def save_model(self, request, obj, form, change):
        package = obj.package
        digest = hashlib.sha256()
        size = 0
        package.seek(0)
        for chunk in package.chunks():
            digest.update(chunk)
            size += len(chunk)
        package.seek(0)
        obj.sha256 = digest.hexdigest()
        obj.package_size = size
        if obj.is_published and not obj.published_at:
            obj.published_at = timezone.now()
        if not obj.is_published:
            obj.published_at = None
        super().save_model(request, obj, form, change)


@admin.register(DesktopUpdateAttempt)
class DesktopUpdateAttemptAdmin(admin.ModelAdmin):
    list_display = ('device', 'release', 'status', 'updated_at')
    list_filter = ('status', 'release', 'device')
    search_fields = ('device__source', 'release__version', 'error')
    readonly_fields = ('device', 'release', 'status', 'error', 'created_at', 'updated_at')

    def has_add_permission(self, request):
        return False

    def has_delete_permission(self, request, obj=None):
        return False
