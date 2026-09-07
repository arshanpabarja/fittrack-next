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
