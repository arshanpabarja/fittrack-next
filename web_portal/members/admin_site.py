from django.contrib.admin import AdminSite
from django.contrib.admin.apps import AdminConfig


class OwnerAdminSite(AdminSite):
    def has_permission(self, request):
        from .permissions import is_owner
        return super().has_permission(request) and is_owner(request.user)


class OwnerAdminConfig(AdminConfig):
    default_site = 'members.admin_site.OwnerAdminSite'
