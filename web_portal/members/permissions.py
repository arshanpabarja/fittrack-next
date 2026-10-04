"""Shared owner/administrator policy; UI visibility never grants permissions."""
from .models import User


def active_account(user):
    return user.is_authenticated and user.is_active and user.status == User.Status.ACTIVE


def is_owner(user):
    return active_account(user) and (user.is_superuser or user.role == User.Role.OWNER)


def is_manager(user):
    return is_owner(user) or (active_account(user) and user.role == User.Role.ADMIN)


def protected_account(user):
    return user.is_superuser or user.role in {User.Role.OWNER, User.Role.ADMIN}
