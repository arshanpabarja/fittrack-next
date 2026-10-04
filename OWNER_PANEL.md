# Gym owner panel

Run `start-owner-panel.ps1`, then open http://127.0.0.1:8000/login.html.
The configured owner phone is 09127124296. Use the password supplied during setup.
Passwords are stored with Django hashing; no owner password is embedded in the website.

Features: combined gym/web directory, member profile and plan edits, debt/payment correction,
website account suspension, CSV download, attendance and website login reports, live plan catalog
updates, coach/workout management through Django admin, and an owner change history.
Reports refresh every 30 seconds. Month means the current Gregorian calendar month in Tehran time.
Website login history starts with installation; historical attendance uses the desktop state database.

The Django database must be the same gym_users.db used by the desktop. Defaults:
- ../database/gym_users.db (relative to FitTrack Next)
- ../database/plans.json
- state/fittrack_next.db
Override with FITTRACK_DB_PATH, FITTRACK_PLANS_PATH, FITTRACK_ATTENDANCE_PATH.
The desktop reads catalog changes when a plan list or enrollment/renewal dialog next loads.
Changing the catalog does not rewrite existing members' purchased plans or consumed sessions.
Both apps must have access to these same files; this is a local installation, not remote cloud sync.

Coach and workout links use /django-admin/. Hardware, face registration, payment terminal operations,
check-in/out and renewals remain in the gym desktop application. Account suspension only blocks website access.

For a fresh database: run `web_portal/manage.py migrate`, then
`web_portal/manage.py setup_owner --mobile 09127124296` (secure password prompt).
The setup command imports existing desktop plans and sets/resets the owner password.
Use Django, not the older lifebox-landing/server.py server, for this panel.
This runserver launcher is for local development, not a public production deployment.

## Operations dashboard

The owner panel at `/owner` has focused views for the dashboard, members,
plans, attendance, recorded renewal payments, and the management audit log.
The existing Persian interface, yellow LifeBox identity, URLs, forms,
Django sessions, CSRF protection, and reception workflows are preserved.
Light and dark themes follow the system initially; a saved manual toggle is available.
On phones, navigation moves into a keyboard-accessible drawer.

`GET /api/owner/overview` is read-only and marked `no-store`; financial totals are owner-only.
It powers active memberships, memberships expiring within seven days, expired
or exhausted memberships, debts, daily attendance, and recorded renewal payments.
Membership validity uses the reception application's one-Jalali-month calendar
rule and session allowance. Unknown dates are kept separate from expired memberships.
The 14-day absence filter requires a recorded last visit and a currently valid
membership; an unavailable attendance source is not treated as no visits.

The dashboard displays a 7- or 30-day payment chart, an hourly attendance chart,
recent renewal payments, and member follow-up queues. Member filters combine
with search, pagination, and CSV export. The renewal-payment view also exports CSV.
Tables provide the underlying payment details; attendance charts have text alternatives.
Local installation reads the reception state database; remote installations use
mirrored records. Unavailable sources show `—`, not a fabricated zero.

**Financial scope:** payment totals include recorded membership renewals only.
They exclude initial purchases, discounts, refunds, and other gym income.
Month totals use the Gregorian month in Tehran time. CSV exports include at most
the 500 newest renewal records shown by the API; dashboard totals use all records.
The existing debt/payment edit fields are accounting corrections, not a payment
terminal charge. Renewals, initial enrollment, and check-in remain in reception.

The remaining brief requires additional domain support: a complete transaction
ledger and receipts, configurable membership durations/freezes, classes and capacity,
member notes and assessments, communication providers, and additional staff permission groups.
Coach and workout management continues through the existing Django admin links.
These are not presented as implemented features in the owner interface.

## Limited administrator

The separate `/admin` panel is for active accounts with role `admin`. Owner accounts
use role `owner`; superusers retain owner access. Migration `0010_owner_role` moves
existing superusers to `owner` without changing their password or member data.
An owner opening the old `/admin` bookmark is redirected to `/owner`.

| Operation | Owner | Administrator |
| --- | --- | --- |
| Member details, debt, follow-up and attendance | Yes | Yes |
| Edit member identity/address/debt or suspend member web account | Yes | Yes |
| View individual renewal payments and export their rows | Yes | Yes |
| Payment totals, payment chart, cumulative member payment field | Yes | No |
| Add/edit catalog plans or change a member's plan/payment field | Yes | No |
| Django admin, roles and protected manager accounts | Yes | No |

`/api/admin/*` and the older `/api/owner/*` routes apply the same role policy.
Administrator responses omit financial totals and payment time series, and member
rows omit the cumulative payment field. Forbidden writes return HTTP 403 before
creating a command or modifying any row. Plan prices can be read individually.
The Django admin site is owner-only even if an administrator has `is_staff` or
model permissions, so it cannot bypass the panel's restrictions.

To provision an administrator, use the owner's Django user-management page, select
the `admin` role and active status, and leave superuser/staff access unchecked.
No administrator account or password is automatically created during deployment.
