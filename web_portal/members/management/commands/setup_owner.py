import getpass
import json
import os
import re
from django.conf import settings
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction
from members.models import Plan, User
from members.views import normalize_digits, MOBILE_RE


class Command(BaseCommand):
    help = 'Create the owner with a hashed password and import desktop plans.'

    def add_arguments(self, parser):
        parser.add_argument('--mobile', required=True)

    def handle(self, *args, **options):
        mobile = normalize_digits(options['mobile'])
        if not MOBILE_RE.fullmatch(mobile):
            raise CommandError('Invalid mobile number')
        password = os.environ.get('FITTRACK_OWNER_PASSWORD') or getpass.getpass('Owner password: ')
        if len(password) < 8:
            raise CommandError('Password must contain at least 8 characters')
        catalog = json.loads(settings.FITTRACK_PLANS_PATH.read_text(encoding='utf-8-sig'))
        with transaction.atomic():
            user, _ = User.objects.get_or_create(mobile=mobile)
            user.role = User.Role.ADMIN
            user.status = User.Status.ACTIVE
            user.is_active = user.is_staff = user.is_superuser = True
            user.first_name = user.first_name or 'مدیر'
            user.set_password(password)
            user.save()
            for local, gender in [('مرد', 'male'), ('زن', 'female'), ('همه', 'all')]:
                for item in catalog.get(local, []):
                    name = item['name']
                    matches = re.findall(r'(\d+)جلسه', normalize_digits(name))
                    price = int(re.sub(r'\D', '', normalize_digits(item.get('price', 0))) or 0)
                    Plan.objects.update_or_create(name=name, defaults=dict(
                        gender=gender, price=price, sessions_per_month=item.get('sessions_per_month') or (int(matches[-1]) if matches else 12),
                        is_active=item.get('is_active', True)))
        self.stdout.write(self.style.SUCCESS('Owner account and desktop plans are ready.'))
