# LifeBox Django production checklist

The website is now served by Django and shares the existing
`database/gym_users.db` with Life Box. Django only adds its own tables; the
legacy `users` table and its 513 current members are preserved.

The workflow is:

1. A visitor creates a web account and membership application (`pending`).
2. Life Box loads the application by mobile number.
3. Reception captures the face and takes payment using the existing desktop flow.
4. Life Box creates the legacy member row and activates the Django application.
5. The website detects `active` status and opens the member dashboard.

Before public deployment:

1. Set strong `DJANGO_SECRET_KEY` and `FITTRACK_DESKTOP_API_TOKEN` values in both the Django and desktop environments.
2. Set `SMS_IR_API_KEY` to a fresh SMS.ir key and `SMS_IR_TEMPLATE_ID=511188`. Never expose the API key in browser code or commit `.env`.
3. Set `DJANGO_DEBUG=0`, configure `DJANGO_ALLOWED_HOSTS`, and put Django behind HTTPS and a production WSGI/ASGI server.
4. Configure `DJANGO_CSRF_TRUSTED_ORIGINS` with the final HTTPS origin.
5. Run `python web_portal/manage.py migrate` before starting the updated site.
6. Back up `database/gym_users.db` regularly. The first pre-Django backup is in `database/backups`.
7. Replace the development admin password and run Django's deployment checks.
