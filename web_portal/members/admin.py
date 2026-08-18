from django.contrib import admin
from django.contrib.auth.admin import UserAdmin

from .models import CoachProfile, MembershipApplication, Plan, User, WorkoutProgram


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

# Register your models here.
