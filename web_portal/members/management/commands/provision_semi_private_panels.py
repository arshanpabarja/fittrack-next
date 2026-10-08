"""Link existing gym members to web accounts without changing gym records."""
import hashlib
import json
import re
import sqlite3
import sys
import unicodedata
from collections import Counter, defaultdict
from contextlib import closing
from pathlib import Path

from django.conf import settings
from django.contrib.auth import authenticate
from django.contrib.auth.hashers import make_password
from django.contrib.auth.password_validation import validate_password
from django.core.management.base import BaseCommand, CommandError
from django.db import connection, transaction
from django.utils import timezone

from app.domain.membership import session_allowance
from members.models import (
    CoachProfile, GymRemoteCommand, GymSyncCursor, GymSyncRecord,
    LegacyMember, MembershipApplication, OwnerAudit, Plan, User,
)


DIGITS = str.maketrans("۰۱۲۳۴۵۶۷۸۹٠١٢٣٤٥٦٧٨٩", "01234567890123456789")


def digits(value):
    return "".join(str(value or "").translate(DIGITS).split())


def canonical(value):
    text = unicodedata.normalize("NFKC", str(value or ""))
    text = text.translate(DIGITS).replace("ي", "ی").replace("ك", "ک")
    return re.sub(r"[\s\u200c\u200d\u200e\u200f]+", "", text)


def digest(value):
    return hashlib.sha256(json.dumps(value, ensure_ascii=False, sort_keys=True,
                                     default=str).encode()).hexdigest()


def snapshot(options):
    members = list(LegacyMember.objects.values().order_by("id"))
    # Biometrics are neither included in reports nor copied into web accounts.
    for member in members:
        embedding, face_image = member.pop("embedding"), member.pop("face_image")
        member["local_face_registered"] = bool(embedding and face_image)
    plans = list(Plan.objects.values().order_by("id"))
    users = list(User.objects.values().order_by("id"))
    applications = list(MembershipApplication.objects.values().order_by("id"))
    profiles = list(CoachProfile.objects.select_related("user").all())
    coach_candidates = [p for p in profiles if
                        canonical(p.user.get_full_name()) == canonical(options["coach_name"])
                        and p.user.role == User.Role.COACH and p.user.status == User.Status.ACTIVE
                        and p.user.is_active]
    issues = []
    coach = coach_candidates[0] if len(coach_candidates) == 1 else None
    if not coach:
        issues.append("Exactly one active coach must match the requested name.")
    by_mobile, web_by_mobile, by_national = defaultdict(list), defaultdict(list), defaultdict(list)
    for member in members:
        by_mobile[digits(member["mobile"])].append(member)
        if digits(member["national_id"]):
            by_national[digits(member["national_id"])].append(member)
    for user in users:
        web_by_mobile[digits(user["mobile"])].append(user)
    apps_by_user = {a["user_id"]: a for a in applications}
    apps_by_member = {a["legacy_member_id"]: a for a in applications if a["legacy_member_id"]}
    mirrored = {r.local_id: r for r in GymSyncRecord.objects.filter(kind="member")}
    cursor = GymSyncCursor.objects.filter(source=settings.FITTRACK_SYNC_SOURCE).first()
    if settings.FITTRACK_REMOTE_SYNC:
        if not cursor or not cursor.sequence:
            issues.append("No successful synchronization for the configured gym.")
        elif (timezone.now() - cursor.updated_at).total_seconds() > options["max_sync_age_hours"] * 3600:
            issues.append("Gym synchronization is too old; synchronize the device first.")
    rows = []
    skipped = Counter()
    excluded = 0
    excluded_mobiles = {digits(value) for value in options.get("exclude_mobile", [])}
    historical_sessions = set(options.get("historical_sessions", []))
    historical_plans = {}
    next_historical_id = min([0] + [p["id"] for p in plans]) - 1
    for member in members:
        if digits(member["mobile"]) in excluded_mobiles:
            excluded += 1
            continue
        if "نیمهخصوصی" not in canonical(member["plan"]):
            continue
        if session_allowance(member["plan"]) not in options["sessions"]:
            skipped[member["plan"]] += 1
            continue
        prefix = f"Gym member {member['id']}: "
        mobile = digits(member["mobile"])
        national = digits(member["national_id"])
        start_issues = len(issues)
        if not re.fullmatch(r"09\d{9}", mobile):
            issues.append(prefix + "invalid mobile number")
        if len(by_mobile[mobile]) != 1:
            issues.append(prefix + "mobile belongs to multiple gym records")
        if not str(member["first_name"]).strip() or not str(member["last_name"]).strip():
            issues.append(prefix + "missing member name")
        if national and not re.fullmatch(r"\d{10}", national):
            issues.append(prefix + "invalid national ID")
        if national and len(by_national[national]) != 1:
            issues.append(prefix + "national ID belongs to multiple gym records")
        gender = {"مرد": "male", "زن": "female", "male": "male", "female": "female"}.get(member["gender"])
        possible = [p for p in plans if p["is_active"] and
                    canonical(p["name"]) == canonical(member["plan"]) and
                    (p["gender"] == "all" or p["gender"] == gender)]
        sessions = session_allowance(member["plan"])
        if not possible and sessions in historical_sessions and gender:
            archived = [p for p in plans if not p["is_active"] and
                        canonical(p["name"]) == canonical(member["plan"]) and
                        (p["gender"] == "all" or p["gender"] == gender)]
            if archived:
                possible = archived
            else:
                key = (canonical(member["plan"]), gender)
                if key not in historical_plans:
                    # Gym sync IDs are strictly positive. Negative IDs cannot
                    # collide with a future device plan and remain site-only.
                    historical_plans[key] = dict(id=next_historical_id, name=member["plan"],
                                                gender=gender, sessions_per_month=sessions,
                                                price=0, is_active=False)
                    next_historical_id -= 1
                possible = [historical_plans[key]]
        if len(possible) != 1:
            issues.append(prefix + "plan does not match exactly one active web plan of the same gender")
        existing = web_by_mobile.get(mobile, [])
        if len(existing) > 1:
            issues.append(prefix + "multiple web accounts use this normalized mobile")
        user = existing[0] if len(existing) == 1 else None
        application = apps_by_user.get(user["id"]) if user else None
        if user:
            if user["role"] != User.Role.MEMBER or user["is_superuser"] or user["is_staff"]:
                issues.append(prefix + "existing web account is not an ordinary member")
            if not user["is_active"] or user["status"] == User.Status.SUSPENDED:
                issues.append(prefix + "existing web account is disabled or suspended")
            if user["mobile"] != mobile:
                issues.append(prefix + "existing web username is not normalized")
            if user["national_id"] and digits(user["national_id"]) != national:
                issues.append(prefix + "web and gym national IDs differ")
        if national and any(u["national_id"] and digits(u["national_id"]) == national and
                            (not user or u["id"] != user["id"]) for u in users):
            issues.append(prefix + "national ID already belongs to another web account")
        if application and application["legacy_member_id"] not in (None, member["id"]):
            issues.append(prefix + "web account is linked to another gym member")
        linked = apps_by_member.get(member["id"])
        if linked and (not user or linked["user_id"] != user["id"]):
            issues.append(prefix + "gym member is linked to another web account")
        mirror = mirrored.get(member["id"])
        if settings.FITTRACK_REMOTE_SYNC and (not mirror or mirror.data.get("mobile") != member["mobile"] or
                                             mirror.data.get("plan") != member["plan"]):
            issues.append(prefix + "member is missing from or differs from synchronized data")
        face_registered = bool(mirror.data.get("face_registered")) if settings.FITTRACK_REMOTE_SYNC and mirror else member["local_face_registered"]
        rows.append(dict(member=member, mobile=mobile, national_id=national, user=user,
                         application=application, plan=possible[0] if len(possible) == 1 else None,
                         face_registered=face_registered, valid=len(issues) == start_issues))
    if not rows:
        issues.append("No matching semi-private members were found.")
    relevant_ids = sorted({r["plan"]["id"] for r in rows if r["plan"]})
    allowed_ids = sorted(coach.allowed_plans.values_list("id", flat=True)) if coach else []
    state = dict(member_identities=[{key: m[key] for key in ("id", "mobile", "national_id")} for m in members],
                 selected_members=[r["member"] for r in rows], plans=plans,
                 users=[{k: v for k, v in u.items() if k not in {"last_login", "date_joined"}} for u in users],
                 applications=applications,
                 coach_id=coach.user_id if coach else None, allowed_ids=allowed_ids,
                 mirrors=sorted((r["member"]["id"], mirrored[r["member"]["id"]].data)
                                for r in rows if r["member"]["id"] in mirrored),
                 sync_source=settings.FITTRACK_SYNC_SOURCE,
                 remote_sync=settings.FITTRACK_REMOTE_SYNC,
                 sessions=sorted(options["sessions"]), coach_name=options["coach_name"],
                 excluded_mobiles=sorted(excluded_mobiles),
                 historical_sessions=sorted(historical_sessions),
                 historical_plans=list(historical_plans.values()))
    report = dict(database=str(connection.settings_dict["NAME"]), remote_sync=settings.FITTRACK_REMOTE_SYNC,
                  synced_at=cursor.updated_at.isoformat() if cursor else None,
                  fingerprint=digest(state), coach_id=coach.user_id if coach else None,
                  members=len(rows), new_accounts=sum(not r["user"] for r in rows),
                  existing_accounts=sum(bool(r["user"]) for r in rows),
                  excluded_gym_records=excluded,
                  historical_plans_to_create=list(historical_plans.values()),
                  plan_counts=dict(Counter(r["member"]["plan"] for r in rows)),
                  plan_ids=relevant_ids, coach_plan_ids_to_add=sorted(set(relevant_ids)-set(allowed_ids)),
                  other_semi_private_plans=dict(skipped), issues=issues,
                  candidates=[dict(gym_id=r["member"]["id"],
                                   name=f"{r['member']['first_name']} {r['member']['last_name']}",
                                   mobile_last4=r["mobile"][-4:],
                                   web_id=r["user"]["id"] if r["user"] else None,
                                   valid=r["valid"]) for r in rows])
    return report, rows, coach


class Command(BaseCommand):
    help = "Audit or provision panels for existing semi-private gym members; dry run is the default."

    def add_arguments(self, parser):
        parser.add_argument("--coach-name", required=True)
        parser.add_argument("--sessions", type=int, nargs="+", default=[8, 12, 16])
        parser.add_argument("--max-sync-age-hours", type=float, default=24)
        parser.add_argument("--exclude-mobile", action="append", default=[])
        parser.add_argument("--historical-sessions", type=int, nargs="+", default=[])
        parser.add_argument("--apply", action="store_true")
        parser.add_argument("--expected-fingerprint")
        parser.add_argument("--password-stdin", action="store_true")
        parser.add_argument("--backup-dir", type=Path)
        parser.add_argument("--summary", action="store_true")

    def handle(self, *args, **options):
        if connection.vendor != "sqlite":
            raise CommandError("This operation requires the configured SQLite database.")
        database = Path(connection.settings_dict["NAME"])
        if not database.is_file():
            raise CommandError("Configured database does not exist; no new database will be created.")
        report, rows, coach = snapshot(options)
        printable = {k: v for k, v in report.items() if k != "candidates"} if options["summary"] else report
        self.stdout.write(json.dumps(printable, ensure_ascii=False, indent=2))
        if not options["apply"]:
            return
        if report["issues"]:
            raise CommandError("Preflight has conflicts. Nothing was changed.")
        if not options["expected_fingerprint"] or options["expected_fingerprint"] != report["fingerprint"]:
            raise CommandError("A matching reviewed preflight fingerprint is required. Nothing was changed.")
        if not options["password_stdin"]:
            raise CommandError("Provide the password on stdin with --password-stdin, not as a command-line argument.")
        password = sys.stdin.readline().rstrip("\r\n")
        validate_password(password)
        backup_dir = options["backup_dir"] or database.parent / "panel_backups"
        backup_dir.mkdir(parents=True, exist_ok=True, mode=0o700)
        backup = backup_dir / f"before-semi-private-panels-{timezone.now():%Y%m%dT%H%M%S%f}.sqlite3"
        # Create restricted permissions before copying any account or member data.
        with backup.open("xb"):
            pass
        backup.chmod(0o600)
        with closing(sqlite3.connect(database.resolve().as_uri() + "?mode=ro", uri=True)) as source:
            if source.execute("PRAGMA quick_check").fetchone()[0] != "ok":
                raise CommandError("Database integrity check failed. Nothing was changed.")
            with closing(sqlite3.connect(backup)) as destination:
                source.backup(destination)
        # Expensive hashing runs before the transaction's write lock, so the
        # live website and device sync only wait for the actual account writes.
        new_passwords = {r["mobile"]: make_password(password) for r in rows if not r["user"]}
        counts = Counter()
        with transaction.atomic():
            current, rows, coach = snapshot(options)
            if current["fingerprint"] != report["fingerprint"] or current["issues"]:
                raise CommandError("Data changed after preflight; rerun the audit. Nothing was changed.")
            source_before = digest(list(LegacyMember.objects.values().order_by("id")))
            commands_before = digest(list(GymRemoteCommand.objects.values().order_by("id")))
            for plan in report["historical_plans_to_create"]:
                Plan.objects.create(**plan)
                counts["historical_plans_created"] += 1
            for row in rows:
                member = row["member"]
                if row["user"]:
                    user = User.objects.get(pk=row["user"]["id"])
                    fields = []
                    if not user.check_password(password):
                        user.set_password(password)
                        fields.append("password")
                        counts["existing_passwords_set"] += 1
                    if user.status != User.Status.ACTIVE:
                        user.status = User.Status.ACTIVE
                        fields.append("status")
                    if fields:
                        user.save(update_fields=fields)
                else:
                    user = User.objects.create(
                        mobile=row["mobile"], password=new_passwords[row["mobile"]],
                        first_name=member["first_name"], last_name=member["last_name"],
                        national_id=row["national_id"] or None, address=member["address"] or "",
                        role=User.Role.MEMBER, status=User.Status.ACTIVE,
                    )
                    counts["accounts_created"] += 1
                application, created = MembershipApplication.objects.get_or_create(
                    user=user, defaults={"plan_id": row["plan"]["id"]})
                desired = dict(plan_id=row["plan"]["id"], legacy_member_id=member["id"],
                               status=MembershipApplication.Status.ACTIVE,
                               paid_amount=max(0, member["payment"] or 0),
                               face_registered=row["face_registered"])
                if not application.activated_at:
                    desired["activated_at"] = timezone.now()
                fields = []
                for key, value in desired.items():
                    if getattr(application, key) != value:
                        setattr(application, key, value)
                        fields.append("plan" if key == "plan_id" else key)
                if fields:
                    application.save(update_fields=fields)
                counts["applications_created" if created else "applications_reused"] += 1
            coach.allowed_plans.add(*report["plan_ids"])
            for row in rows:
                user = authenticate(mobile=row["mobile"], password=password)
                if not user or user.role != User.Role.MEMBER or user.status != User.Status.ACTIVE:
                    raise CommandError("Account authentication verification failed; changes rolled back.")
                application = user.membership_application
                if application.legacy_member_id != row["member"]["id"] or application.plan_id != row["plan"]["id"]:
                    raise CommandError("Member linkage verification failed; changes rolled back.")
            from members.views import _coach_member_queryset
            coach_mobile_set = set(_coach_member_queryset(coach.user).values_list("mobile", flat=True))
            if not {r["mobile"] for r in rows}.issubset(coach_mobile_set):
                raise CommandError("Coach access verification failed; changes rolled back.")
            if digest(list(LegacyMember.objects.values().order_by("id"))) != source_before or digest(list(GymRemoteCommand.objects.values().order_by("id"))) != commands_before:
                raise CommandError("Gym records changed; changes rolled back.")
            OwnerAudit.objects.create(actor=None, action=f"Provisioned {len(rows)} semi-private panels for coach {coach.user_id}")
        self.stdout.write(json.dumps(dict(ok=True, verified_members=len(rows),
                                          backup=str(backup), **counts), ensure_ascii=False))
