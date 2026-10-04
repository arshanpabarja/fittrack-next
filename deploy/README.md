# دیپلوی پنل لایف‌باکس

بستهٔ وب شامل رابط سایت، Django، migrationها و فقط ماژول‌های سبک تقویم و عضویت
در `app/domain` است. PyQt، مدل چهره، اطلاعات اعضا و رمزهای محیط محلی در بسته نیستند.

## ساخت بسته روی رایانه توسعه

```powershell
.\.venv\Scripts\python.exe build_web_release.py
.\.venv\Scripts\python.exe validate_web_release.py
```

خروجی `dist/lifebox-web.zip` است. دستور دوم همان بسته را در پوشهٔ موقت استخراج
می‌کند و با تنظیمات production و دیتابیس آزمایشی تازه، پنل و امنیت آن را می‌آزماید.
هیچ اتصال یا انتقالی به باشگاه انجام نمی‌شود.

## به‌روزرسانی VPS موجود

۱. از دیتابیس واقعی با SQLite Backup API یا در زمان توقف سرویس نسخهٔ پشتیبان بگیرید.
ZIP را ابتدا در پوشهٔ موقت سرور باز کنید و `web_portal`، `lifebox-landing`، `app`
و `deploy` آن را به `/var/www/lifebox/` منتقل کنید. دیتابیس، state، محیط محرمانه
و فایل سرویس فعلی را جایگزین نکنید. پوشهٔ `app` بسته فقط دو ماژول کسب‌وکار دارد.

۲. در محیط مجازی سرور وابستگی‌های مخصوص وب را نصب کنید:
Python سرور باید نسخهٔ ۳٫۱۰ یا بالاتر باشد. نسخهٔ Gunicorn بر اساس
[انتشار رسمی 26.2.0](https://pypi.org/project/gunicorn/26.2.0/) ثابت شده است.

```bash
/var/www/venv/bin/pip install -r /var/www/lifebox/deploy/requirements-web.txt
```

۳. مقادیر `deploy.env.example` را در EnvironmentFile واقعی سرویس وارد کنید؛ فایل
`.env` به‌صورت خودکار خوانده نمی‌شود. `DJANGO_DEBUG=0` تنظیمات امن HTTPS، کوکی‌ها
و HSTS را فعال می‌کند. دامنه‌ها باید بدون `https://` در `DJANGO_ALLOWED_HOSTS`
و به‌صورت origin کامل HTTPS در `DJANGO_CSRF_TRUSTED_ORIGINS` باشند.

کلید محرمانهٔ معتبر فعلی Django را حفظ کنید. برای نصب تازه، مقدار تصادفی بسازید:

```bash
/var/www/venv/bin/python -c "import secrets; print(secrets.token_urlsafe(64))"
```

کلید پیامک قبلاً داخل کد بود؛ آن را در حساب SMS.ir تعویض کنید و کلید تازه را فقط
در `SMS_IR_API_KEY` سرویس بگذارید. رمزها را در ZIP یا Git قرار ندهید. دسترسی
EnvironmentFile را به root/مدیر سرویس محدود کنید. شناسه و توکن sync نصب فعال
باشگاه باید حفظ شوند؛ مقدار جدید را فقط با تغییر هماهنگ دستگاه باشگاه تنظیم کنید.

۴. با همان کاربر، Python و متغیرهای محیطی سرویس این دستورها را اجرا کنید:

```bash
cd /var/www/lifebox/web_portal
/var/www/venv/bin/python manage.py check --deploy --fail-level ERROR
/var/www/venv/bin/python manage.py migrate --noinput
/var/www/venv/bin/python manage.py collectstatic --noinput
```

سرویس با تنظیمات ناقص production متوقف می‌شود و فقط نام تنظیم ناقص را گزارش می‌کند.
مسیر صریح `FITTRACK_DB_PATH` باید بیرون پوشهٔ کد باشد و پوشه و دیتابیس برای
کاربر سرویس قابل نوشتن باشند. نمونهٔ سرویس و Nginx برای تطبیق با VPS موجود در
این پوشه قرار دارند؛ از جایگزینی مستقیم تنظیمات SSL یا سرویس فعال خودداری کنید.

۵. Gunicorn روی `127.0.0.1` اجرا شود. Nginx باید `X-Forwarded-Proto` را خودش
بازنویسی کند؛ فقط در این حالت `DJANGO_TRUST_PROXY_SSL=1` بگذارید. برای جلوگیری
از حلقهٔ redirect، مقدار header و TLS واقعی Nginx را بررسی کنید. اگر CDN دارید،
ارتباط CDN تا VPS هم HTTPS باشد. نمونهٔ اجرا:

```bash
/var/www/venv/bin/gunicorn --config /var/www/lifebox/deploy/gunicorn.conf.py config.wsgi:application
```

فایل‌های `/static/` از خروجی collectstatic و `/assets/` از پوشهٔ assets سرو شوند.
صفحات HTML، به‌خصوص `/admin`، باید از Django عبور کنند. `/api/*` در Nginx و CDN
کش نشوند. یک worker با چهار thread تعریف شده است تا محدودیت پیامک با cache
درون‌پردازه‌ای فعلی حفظ شود؛ برای چند worker ابتدا cache اشتراکی تعریف کنید.
HSTS با یک ساعت شروع می‌شود و پس از تأیید HTTPS می‌توان مدت آن را افزایش داد.
دو هشدار اختیاری `security.W005` و `security.W021` برای HSTS تمام زیردامنه‌ها و
ثبت در فهرست preload انتظار می‌روند؛ این دو سیاست فقط پس از تأیید HTTPS تمام
زیردامنه‌ها فعال شوند. هشدارهای دیگر باید پیش از راه‌اندازی رفع شوند؛ آزمون ZIP
هر هشدار دیگری را رد می‌کند.

۶. بعد از restart سرویس، ورود مدیر، بارگذاری `/admin`، آمار، یک ویرایش آزمایشی
و دریافت آخرین sync را بررسی کنید. دستورهای پایهٔ بررسی آنلاین:

```bash
curl -I http://lifeboxgym.com/admin
curl -I https://lifeboxgym.com/admin
curl -I https://lifeboxgym.com/owner.css
curl -I https://lifeboxgym.com/assets/Vazirmatn-Variable.ttf
```

HTTP باید به HTTPS و پنل بدون ورود باید به صفحهٔ ورود هدایت شود. آزمون رفت‌وبرگشت
با دستگاه روشن باشگاه طبق `CLOUD_DEPLOYMENT.md` انجام شود. ساخت بسته و آزمون
محلی production به‌تنهایی عملکرد شبکه، SMS.ir یا SSL سرور واقعی را تأیید نمی‌کند.

پنل مالک در `/owner` و پنل ادمین محدود در `/admin` است. migration جدید نقش
superuserهای موجود را به `owner` تبدیل می‌کند؛ رمزها تغییری نمی‌کنند. ادمین
معمولی مجموع پرداخت‌ها و نمودار مالی را دریافت نمی‌کند و اجازهٔ تغییر پلن ندارد.
نقش ادمین را از مدیریت کاربران Django با حساب مالک تعیین کنید؛ حساب جدیدی
به‌صورت خودکار ساخته نمی‌شود.

مبنای تنظیمات امن: [چک‌لیست رسمی استقرار Django](https://docs.djangoproject.com/en/5.2/howto/deployment/checklist/).
