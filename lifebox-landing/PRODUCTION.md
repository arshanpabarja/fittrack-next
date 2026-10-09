# LifeBox Django production checklist

For the current owner panel, build `dist/lifebox-web.zip` with
`build_web_release.py`, validate it with `validate_web_release.py`, and follow
`deploy/README.md`. The release includes the required shared membership modules
under `app/domain`, plus web-only dependencies and Gunicorn/Nginx examples.
`DJANGO_DEBUG=0` enables secure cookies, HTTPS redirect and a one-hour HSTS policy;
startup refuses missing/default production secrets or missing explicit paths.
The former SMS key has been removed from source and must be rotated in SMS.ir,
then provided through the service environment as `SMS_IR_API_KEY`.

## Public search metadata

The public pages use `https://lifeboxgym.com` as their canonical origin. If the
production domain changes, update the canonical/Open Graph URLs in the five public
HTML pages, the HealthClub JSON-LD in `index.html`, and the origin in `robots.txt`
and `sitemap.xml` together.

The sitemap includes only the five public canonical pages. Keep account pages,
private panels, API endpoints and legacy `.html` redirects out of it. Update each
page's `lastmod` when its content, structured data or links change significantly;
use the actual page modification date, not the sitemap generation or deployment
date. The current dates reflect the public-page changes committed on 2026-10-04.

Deploy `assets/optimized/` along with the HTML, `app.js`, `robots.txt`, and
`sitemap.xml`. Both Django and the standalone Python server serve the crawler
files at the site root. If Nginx serves static files directly, ensure those two
root URLs reach Django or the matching files, and serve WebP as `image/webp`.

After deployment, verify `/robots.txt` and `/sitemap.xml` return HTTP 200, validate
the homepage JSON-LD with Google's Rich Results Test, and submit the sitemap in
Google Search Console. Search Console access is required to inspect indexing and
search performance; these source changes do not submit the site automatically.

The WebP variants preserve the supplied photos. Original PNGs remain available;
public pages use responsive WebP images. Gallery videos load on demand and the
hero autoplays after page load only on desktop without reduced motion, data-saving
mode, or a reported 2G connection.

## Account deployment

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
