from django.urls import path, re_path

from . import views


urlpatterns = [
    path("", views.page, {"name": "index.html"}),
    path("index.html", views.page, {"name": "index.html"}),
    path("coaches.html", views.page, {"name": "coaches.html"}),
    path("login.html", views.page, {"name": "login.html"}),
    path("signup.html", views.page, {"name": "signup.html"}),
    path("pending.html", views.page, {"name": "pending.html"}),
    path("dashboard.html", views.page, {"name": "dashboard.html"}),
    path("admin.html", views.page, {"name": "admin.html"}),
    path("coach-panel.html", views.page, {"name": "coach-panel.html"}),
    path("styles.css", views.public_file, {"name": "styles.css"}),
    path("app.js", views.public_file, {"name": "app.js"}),
    re_path(r"^assets/(?P<name>.+)$", views.asset_file),
    path("api/health", views.health),
    path("api/plans", views.plans_api),
    path("api/signup", views.signup_api),
    path("api/login", views.login_api),
    path("api/logout", views.logout_api),
    path("api/me", views.me_api),
    path("api/admin/users", views.admin_users_api),
    path("api/admin/users/<int:user_id>/status", views.admin_user_status_api),
    path("api/coach/profile", views.coach_profile_api),
    path("api/coach/members", views.coach_members_api),
    path("api/coach/programs", views.coach_programs_api),
    path("api/coach/programs/<int:program_id>", views.coach_program_api),
    path("api/member/program", views.member_program_api),
    path("api/desktop/coaches", views.desktop_coaches_api),
    path("api/desktop/coaches/<int:coach_id>", views.desktop_coach_api),
    path("api/desktop/members/<int:legacy_member_id>/password", views.desktop_member_password_api),
    path("api/desktop/applications", views.desktop_applications_api),
    path("api/desktop/applications/<int:application_id>/activate", views.desktop_activate_api),
]
