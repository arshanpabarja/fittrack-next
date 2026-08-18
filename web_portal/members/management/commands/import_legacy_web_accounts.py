import sqlite3
from datetime import datetime

from django.conf import settings
from django.core.management.base import BaseCommand
from django.db import transaction
from django.utils import timezone

from members.models import LegacyMember, MembershipApplication, Plan, User


DIGITS = str.maketrans("۰۱۲۳۴۵۶۷۸۹٠١٢٣٤٥٦٧٨٩", "01234567890123456789")


def normalize(value):
    return "".join(str(value or "").translate(DIGITS).split())


class Command(BaseCommand):
    help = "Import accounts from the pre-Django LifeBox database while preserving their passwords."

    def handle(self, *args, **options):
        source = settings.BASE_DIR.parent / "lifebox-landing" / "data" / "lifebox_web.db"
        if not source.is_file():
            self.stdout.write("Legacy web database was not found; nothing to import.")
            return
        with sqlite3.connect(source) as connection:
            connection.row_factory = sqlite3.Row
            rows = connection.execute("SELECT * FROM accounts WHERE role != 'admin' ORDER BY id").fetchall()
        plans = list(Plan.objects.filter(is_active=True))
        if not plans:
            self.stderr.write("No active plans exist. Run seed_plans first.")
            return
        legacy_members = list(LegacyMember.objects.all())
        imported = skipped = 0
        for row in rows:
            mobile = normalize(row["mobile"])
            if User.objects.filter(mobile=mobile).exists():
                skipped += 1
                continue
            legacy = next((member for member in legacy_members if normalize(member.mobile) == mobile), None)
            full_name = " ".join(str(row["full_name"] or "").split())
            first_name, _, last_name = full_name.partition(" ")
            plan = next((item for item in plans if item.name == row["plan"]), plans[0])
            active = legacy is not None and row["status"] == "active"
            joined_at = timezone.now()
            try:
                parsed = datetime.fromisoformat(row["joined_at"])
                joined_at = parsed if timezone.is_aware(parsed) else timezone.make_aware(parsed)
            except (TypeError, ValueError):
                pass
            encoded = str(row["password_hash"] or "")
            if encoded.startswith("pbkdf2_sha256$"):
                encoded = encoded.replace("pbkdf2_sha256$", "lifebox_pbkdf2_sha256$", 1)
            with transaction.atomic():
                user = User(
                    mobile=mobile,
                    first_name=first_name,
                    last_name=last_name,
                    national_id=legacy.national_id if legacy and legacy.national_id else None,
                    address=legacy.address if legacy and legacy.address else "",
                    role=User.Role.MEMBER,
                    status=User.Status.ACTIVE if active else User.Status.PENDING,
                    password=encoded,
                    date_joined=joined_at,
                )
                user.save()
                MembershipApplication.objects.create(
                    user=user,
                    plan=plan,
                    status=MembershipApplication.Status.ACTIVE if active else MembershipApplication.Status.PENDING,
                    legacy_member_id=legacy.id if active else None,
                    activated_at=timezone.now() if active else None,
                    face_registered=active,
                )
            imported += 1
        self.stdout.write(self.style.SUCCESS(f"Legacy accounts: {imported} imported, {skipped} skipped."))
