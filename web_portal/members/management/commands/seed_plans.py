import json
import re

from django.conf import settings
from django.core.management.base import BaseCommand

from members.models import Plan


DIGITS = str.maketrans("۰۱۲۳۴۵۶۷۸۹٠١٢٣٤٥٦٧٨٩", "01234567890123456789")


def number(value):
    digits = re.sub(r"\D", "", str(value or "").translate(DIGITS))
    return int(digits or 0)


class Command(BaseCommand):
    help = "Import membership plans from Life Box plans.json without deleting existing plans."

    def handle(self, *args, **options):
        source = settings.BASE_DIR.parent / "database" / "plans.json"
        data = json.loads(source.read_text(encoding="utf-8"))
        created = updated = 0
        gender_map = {"مرد": Plan.Gender.MALE, "زن": Plan.Gender.FEMALE}
        for gender_name, items in data.items():
            if not isinstance(items, list):
                continue
            for item in items:
                name = str(item.get("name", "")).strip()
                if not name:
                    continue
                session_matches = re.findall(r"\d+", name.translate(DIGITS))
                sessions = int(session_matches[-1]) if session_matches else 0
                _, was_created = Plan.objects.update_or_create(
                    name=name,
                    defaults={
                        "gender": gender_map.get(gender_name, Plan.Gender.ALL),
                        "price": number(item.get("price")),
                        "sessions_per_month": sessions,
                        "is_active": True,
                    },
                )
                created += int(was_created)
                updated += int(not was_created)
        self.stdout.write(self.style.SUCCESS(f"Plans ready: {created} created, {updated} updated."))
