"""LifeBox local production baseline: static site, accounts, sessions, and admin API."""

from __future__ import annotations

import base64
import hashlib
import hmac
import json
import mimetypes
import os
import re
import secrets
import sqlite3
import threading
import time
from collections import defaultdict, deque
from datetime import datetime, timezone
from email.utils import formatdate
from http import HTTPStatus
from http.cookies import SimpleCookie
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, unquote, urlparse


ROOT = Path(__file__).resolve().parent
DATA_DIR = ROOT / "data"
DB_PATH = DATA_DIR / "lifebox_web.db"
FITTRACK_DB_PATH = Path(
    os.getenv("FITTRACK_DB_PATH", str(ROOT.parent.parent / "database" / "gym_users.db"))
).resolve()
HOST = os.getenv("LIFEBOX_HOST", "192.168.100.95")
PORT = int(os.getenv("LIFEBOX_PORT", "8000"))
ENVIRONMENT = os.getenv("LIFEBOX_ENV", "development").strip().lower()
USE_HTTPS = os.getenv("LIFEBOX_HTTPS", "0") == "1"
SESSION_SECONDS = int(os.getenv("LIFEBOX_SESSION_SECONDS", str(60 * 60 * 24 * 7)))
ADMIN_MOBILE = os.getenv("LIFEBOX_ADMIN_MOBILE", "09120000000")
ADMIN_PASSWORD = os.getenv("LIFEBOX_ADMIN_PASSWORD", "LifeBox@1405")
ROTATE_ADMIN_PASSWORD = os.getenv("LIFEBOX_ROTATE_ADMIN_PASSWORD", "0") == "1"
MOBILE_RE = re.compile(r"^09\d{9}$")
DIGIT_TRANSLATION = str.maketrans("۰۱۲۳۴۵۶۷۸۹٠١٢٣٤٥٦٧٨٩", "01234567890123456789")
PUBLIC_PAGES = {
    "/index.html",
    "/coaches.html",
    "/login.html",
    "/signup.html",
    "/dashboard.html",
    "/admin.html",
    "/styles.css",
    "/app.js",
}
PUBLIC_ASSET_EXTENSIONS = {".png", ".jpg", ".jpeg", ".webp", ".ico", ".ttf", ".woff2", ".mp4", ".webm"}
RATE_BUCKETS: dict[str, deque[float]] = defaultdict(deque)
RATE_LOCK = threading.Lock()


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def connect() -> sqlite3.Connection:
    connection = sqlite3.connect(DB_PATH, timeout=8)
    connection.row_factory = sqlite3.Row
    connection.execute("PRAGMA foreign_keys = ON")
    connection.execute("PRAGMA busy_timeout = 8000")
    return connection


def connect_fittrack() -> sqlite3.Connection:
    """Open Life Box's member database in read-only mode."""
    connection = sqlite3.connect(f"file:{FITTRACK_DB_PATH.as_posix()}?mode=ro", uri=True, timeout=8)
    connection.row_factory = sqlite3.Row
    connection.execute("PRAGMA query_only = ON")
    connection.execute("PRAGMA busy_timeout = 8000")
    return connection


def normalize_mobile(value: object) -> str:
    return re.sub(r"\s+", "", str(value or "").translate(DIGIT_TRANSLATION))


def fittrack_member(mobile: str) -> sqlite3.Row | None:
    normalized = normalize_mobile(mobile)
    if not FITTRACK_DB_PATH.is_file():
        return None
    with connect_fittrack() as db:
        rows = db.execute(
            """
            SELECT id, first_name, last_name, mobile, plan, used_sessions, signup_time
            FROM users ORDER BY id DESC
            """
        ).fetchall()
    return next((row for row in rows if normalize_mobile(row["mobile"]) == normalized), None)


def fittrack_members(search: str = "") -> list[sqlite3.Row]:
    if not FITTRACK_DB_PATH.is_file():
        return []
    needle = search.strip().casefold()
    normalized_needle = normalize_mobile(search)
    with connect_fittrack() as db:
        rows = db.execute(
            """
            SELECT id, first_name, last_name, mobile, plan, used_sessions, signup_time
            FROM users ORDER BY id DESC LIMIT 1000
            """
        ).fetchall()
    if not needle:
        return rows
    return [
        row
        for row in rows
        if needle in f'{row["first_name"] or ""} {row["last_name"] or ""}'.casefold()
        or normalized_needle in normalize_mobile(row["mobile"])
    ]


def hash_password(password: str, salt: bytes | None = None) -> str:
    salt = salt or secrets.token_bytes(16)
    digest = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt, 310_000)
    return f"pbkdf2_sha256$310000${base64.urlsafe_b64encode(salt).decode()}${base64.urlsafe_b64encode(digest).decode()}"


def verify_password(password: str, encoded: str) -> bool:
    try:
        algorithm, rounds, salt_b64, digest_b64 = encoded.split("$", 3)
        if algorithm != "pbkdf2_sha256":
            return False
        salt = base64.urlsafe_b64decode(salt_b64.encode())
        expected = base64.urlsafe_b64decode(digest_b64.encode())
        actual = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt, int(rounds))
        return hmac.compare_digest(actual, expected)
    except (ValueError, TypeError):
        return False


def password_is_strong(password: str) -> bool:
    return len(password) >= 10 and bool(re.search(r"[A-Za-z]", password)) and bool(re.search(r"\d", password))


def init_database() -> None:
    DATA_DIR.mkdir(exist_ok=True)
    with connect() as db:
        db.execute("PRAGMA journal_mode = WAL")
        db.execute("PRAGMA synchronous = NORMAL")
        db.execute(
            """
            CREATE TABLE IF NOT EXISTS accounts (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                full_name TEXT NOT NULL,
                mobile TEXT NOT NULL UNIQUE,
                password_hash TEXT NOT NULL,
                role TEXT NOT NULL DEFAULT 'member' CHECK(role IN ('member', 'admin')),
                status TEXT NOT NULL DEFAULT 'active' CHECK(status IN ('active', 'inactive')),
                plan TEXT NOT NULL DEFAULT 'عضویت شروع',
                sessions_used INTEGER NOT NULL DEFAULT 0,
                joined_at TEXT NOT NULL,
                last_login_at TEXT
            )
            """
        )
        db.execute(
            """
            CREATE TABLE IF NOT EXISTS sessions (
                token_hash TEXT PRIMARY KEY,
                account_id INTEGER NOT NULL,
                expires_at INTEGER NOT NULL,
                created_at TEXT NOT NULL,
                FOREIGN KEY(account_id) REFERENCES accounts(id) ON DELETE CASCADE
            )
            """
        )
        db.execute("CREATE UNIQUE INDEX IF NOT EXISTS idx_accounts_mobile ON accounts(mobile)")
        db.execute("CREATE INDEX IF NOT EXISTS idx_sessions_account_id ON sessions(account_id)")
        db.execute("CREATE INDEX IF NOT EXISTS idx_sessions_expires_at ON sessions(expires_at)")
        db.execute("DELETE FROM sessions WHERE expires_at < ?", (int(time.time()),))
        existing = db.execute("SELECT id FROM accounts WHERE mobile = ?", (ADMIN_MOBILE,)).fetchone()
        if not existing:
            if ENVIRONMENT == "production" and ADMIN_PASSWORD == "LifeBox@1405":
                raise RuntimeError("Set LIFEBOX_ADMIN_PASSWORD before the first production start.")
            db.execute(
                """
                INSERT INTO accounts
                    (full_name, mobile, password_hash, role, status, plan, sessions_used, joined_at)
                VALUES (?, ?, ?, 'admin', 'active', 'مدیریت مجموعه', 0, ?)
                """,
                ("مدیر لایف‌باکس", ADMIN_MOBILE, hash_password(ADMIN_PASSWORD), now_iso()),
            )
        elif ROTATE_ADMIN_PASSWORD:
            if ADMIN_PASSWORD == "LifeBox@1405":
                raise RuntimeError("Refusing to rotate the admin account to the default password.")
            db.execute(
                "UPDATE accounts SET password_hash = ? WHERE mobile = ? AND role = 'admin'",
                (hash_password(ADMIN_PASSWORD), ADMIN_MOBILE),
            )
            db.execute(
                "DELETE FROM sessions WHERE account_id = (SELECT id FROM accounts WHERE mobile = ? AND role = 'admin')",
                (ADMIN_MOBILE,),
            )
        db.execute("PRAGMA optimize")


def public_account(row: sqlite3.Row) -> dict:
    payload = {
        "id": row["id"],
        "fullName": row["full_name"],
        "mobile": row["mobile"],
        "role": row["role"],
        "status": row["status"],
        "plan": row["plan"],
        "sessionsUsed": row["sessions_used"],
        "joinedAt": row["joined_at"],
        "lastLoginAt": row["last_login_at"],
        "webLinked": True,
    }
    if row["role"] == "member":
        member = fittrack_member(row["mobile"])
        if member:
            payload.update(
                {
                    "fullName": f'{member["first_name"] or ""} {member["last_name"] or ""}'.strip(),
                    "mobile": normalize_mobile(member["mobile"]),
                    "plan": member["plan"] or payload["plan"],
                    "sessionsUsed": member["used_sessions"] or 0,
                    "joinedAt": member["signup_time"] or payload["joinedAt"],
                    "fittrackLinked": True,
                }
            )
        else:
            payload["fittrackLinked"] = False
    return payload


def public_fittrack_member(row: sqlite3.Row, account: sqlite3.Row | None = None) -> dict:
    return {
        "id": account["id"] if account else f'fittrack-{row["id"]}',
        "fullName": f'{row["first_name"] or ""} {row["last_name"] or ""}'.strip(),
        "mobile": normalize_mobile(row["mobile"]),
        "role": account["role"] if account else "member",
        "status": account["status"] if account else "active",
        "plan": row["plan"] or "—",
        "sessionsUsed": row["used_sessions"] or 0,
        "joinedAt": row["signup_time"],
        "lastLoginAt": account["last_login_at"] if account else None,
        "webLinked": account is not None,
        "fittrackLinked": True,
    }


def limited(key: str, limit: int, window_seconds: int) -> bool:
    now = time.monotonic()
    with RATE_LOCK:
        bucket = RATE_BUCKETS[key]
        while bucket and bucket[0] <= now - window_seconds:
            bucket.popleft()
        if len(bucket) >= limit:
            return True
        bucket.append(now)
        return False


class LifeBoxHTTPServer(ThreadingHTTPServer):
    daemon_threads = True
    allow_reuse_address = True


class LifeBoxHandler(BaseHTTPRequestHandler):
    server_version = "LifeBox"
    sys_version = ""

    def log_message(self, fmt: str, *args) -> None:
        print(f"[{self.log_date_time_string()}] {self.client_address[0]} {fmt % args}")

    def end_headers(self) -> None:
        self.send_header("X-Content-Type-Options", "nosniff")
        self.send_header("X-Frame-Options", "DENY")
        self.send_header("Referrer-Policy", "strict-origin-when-cross-origin")
        self.send_header("Permissions-Policy", "camera=(), microphone=(), geolocation=(), payment=()")
        self.send_header(
            "Content-Security-Policy",
            "default-src 'self'; script-src 'self'; style-src 'self'; img-src 'self' data:; "
            "media-src 'self'; connect-src 'self'; object-src 'none'; base-uri 'self'; "
            "frame-ancestors 'none'; form-action 'self'",
        )
        if USE_HTTPS:
            self.send_header("Strict-Transport-Security", "max-age=31536000; includeSubDomains")
        if self.path.startswith("/api/") or self.path.endswith(".html") or self.path == "/":
            self.send_header("Cache-Control", "no-store")
        elif self.path.startswith("/assets/"):
            self.send_header("Cache-Control", "public, max-age=86400")
        else:
            self.send_header("Cache-Control", "no-cache")
        super().end_headers()

    def send_json(
        self,
        payload: dict | list,
        status: int = HTTPStatus.OK,
        cookie: str | None = None,
        retry_after: int | None = None,
    ) -> None:
        body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        if cookie:
            self.send_header("Set-Cookie", cookie)
        if retry_after:
            self.send_header("Retry-After", str(retry_after))
        self.end_headers()
        self.wfile.write(body)

    def read_json(self) -> dict | None:
        try:
            length = int(self.headers.get("Content-Length", "0"))
            if length <= 0 or length > 16_384:
                return None
            payload = json.loads(self.rfile.read(length).decode("utf-8"))
            return payload if isinstance(payload, dict) else None
        except (ValueError, UnicodeDecodeError, json.JSONDecodeError):
            return None

    def client_ip(self) -> str:
        return self.client_address[0]

    def origin_is_safe(self) -> bool:
        origin = self.headers.get("Origin")
        if not origin:
            return True
        parsed = urlparse(origin)
        return parsed.netloc.lower() == self.headers.get("Host", "").lower() and parsed.scheme in {"http", "https"}

    def reject_unsafe_origin(self) -> bool:
        if self.origin_is_safe():
            return False
        self.send_json({"ok": False, "message": "درخواست از مبدأ نامعتبر رد شد."}, HTTPStatus.FORBIDDEN)
        return True

    def session_token(self) -> str | None:
        cookie = SimpleCookie(self.headers.get("Cookie", ""))
        morsel = cookie.get("lifebox_session")
        return morsel.value if morsel else None

    def current_account(self) -> sqlite3.Row | None:
        token = self.session_token()
        if not token:
            return None
        token_hash = hashlib.sha256(token.encode()).hexdigest()
        with connect() as db:
            return db.execute(
                """
                SELECT accounts.* FROM sessions
                JOIN accounts ON accounts.id = sessions.account_id
                WHERE sessions.token_hash = ? AND sessions.expires_at > ? AND accounts.status = 'active'
                """,
                (token_hash, int(time.time())),
            ).fetchone()

    def create_session(self, account_id: int) -> str:
        token = secrets.token_urlsafe(32)
        token_hash = hashlib.sha256(token.encode()).hexdigest()
        with connect() as db:
            db.execute("DELETE FROM sessions WHERE account_id = ? AND expires_at < ?", (account_id, int(time.time())))
            db.execute(
                "INSERT INTO sessions (token_hash, account_id, expires_at, created_at) VALUES (?, ?, ?, ?)",
                (token_hash, account_id, int(time.time()) + SESSION_SECONDS, now_iso()),
            )
        secure = "; Secure" if USE_HTTPS else ""
        return f"lifebox_session={token}; Path=/; HttpOnly; SameSite=Strict; Max-Age={SESSION_SECONDS}{secure}"

    def expired_session_cookie(self) -> str:
        secure = "; Secure" if USE_HTTPS else ""
        return f"lifebox_session=; Path=/; HttpOnly; SameSite=Strict; Max-Age=0{secure}"

    def require_account(self, role: str | None = None) -> sqlite3.Row | None:
        account = self.current_account()
        if not account:
            self.send_json({"ok": False, "message": "برای ادامه وارد حساب شوید."}, HTTPStatus.UNAUTHORIZED)
            return None
        if role and account["role"] != role:
            self.send_json({"ok": False, "message": "دسترسی به این بخش مجاز نیست."}, HTTPStatus.FORBIDDEN)
            return None
        return account

    def static_file(self) -> Path | None:
        raw_path = unquote(urlparse(self.path).path)
        request_path = "/index.html" if raw_path == "/" else raw_path
        if request_path in PUBLIC_PAGES:
            relative = request_path.lstrip("/")
        elif request_path.startswith("/assets/") and Path(request_path).suffix.lower() in PUBLIC_ASSET_EXTENSIONS:
            relative = request_path.lstrip("/")
        else:
            return None
        candidate = (ROOT / relative).resolve()
        try:
            candidate.relative_to(ROOT)
        except ValueError:
            return None
        return candidate if candidate.is_file() else None

    def serve_static(self, head_only: bool = False) -> None:
        path = self.static_file()
        if not path:
            self.send_error(HTTPStatus.NOT_FOUND, "Not found")
            return
        file_size = path.stat().st_size
        content_type = mimetypes.guess_type(str(path))[0] or "application/octet-stream"
        start, end = 0, file_size - 1
        status = HTTPStatus.OK
        range_header = self.headers.get("Range")
        if range_header:
            match = re.fullmatch(r"bytes=(\d*)-(\d*)", range_header.strip())
            if not match:
                self.send_error(HTTPStatus.REQUESTED_RANGE_NOT_SATISFIABLE)
                return
            first, last = match.groups()
            if first:
                start = int(first)
                end = min(int(last), file_size - 1) if last else file_size - 1
            elif last:
                length = min(int(last), file_size)
                start, end = file_size - length, file_size - 1
            if start < 0 or start >= file_size or end < start:
                self.send_response(HTTPStatus.REQUESTED_RANGE_NOT_SATISFIABLE)
                self.send_header("Content-Range", f"bytes */{file_size}")
                self.end_headers()
                return
            status = HTTPStatus.PARTIAL_CONTENT
        length = end - start + 1
        self.send_response(status)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(length))
        self.send_header("Accept-Ranges", "bytes")
        self.send_header("Last-Modified", formatdate(path.stat().st_mtime, usegmt=True))
        if status == HTTPStatus.PARTIAL_CONTENT:
            self.send_header("Content-Range", f"bytes {start}-{end}/{file_size}")
        self.end_headers()
        if head_only:
            return
        with path.open("rb") as source:
            source.seek(start)
            remaining = length
            while remaining:
                chunk = source.read(min(64 * 1024, remaining))
                if not chunk:
                    break
                self.wfile.write(chunk)
                remaining -= len(chunk)

    def do_HEAD(self) -> None:
        self.serve_static(head_only=True)

    def do_GET(self) -> None:
        parsed = urlparse(self.path)
        if parsed.path == "/api/health":
            self.send_json({"ok": True, "service": "LifeBox"})
            return
        if parsed.path == "/api/me":
            account = self.require_account()
            if account:
                self.send_json({"ok": True, "user": public_account(account)})
            return
        if parsed.path == "/api/admin/users":
            account = self.require_account("admin")
            if not account:
                return
            query = parse_qs(parsed.query)
            search = query.get("search", [""])[0].strip()[:80]
            with connect() as db:
                accounts = db.execute("SELECT * FROM accounts ORDER BY id DESC LIMIT 1000").fetchall()
            accounts_by_mobile = {normalize_mobile(row["mobile"]): row for row in accounts}
            members = fittrack_members(search)
            users = [
                public_fittrack_member(member, accounts_by_mobile.pop(normalize_mobile(member["mobile"]), None))
                for member in members
            ]
            if not search:
                users.extend(public_account(row) for row in accounts_by_mobile.values())
            else:
                needle = search.casefold()
                users.extend(
                    public_account(row)
                    for row in accounts_by_mobile.values()
                    if needle in row["full_name"].casefold()
                    or normalize_mobile(search) in normalize_mobile(row["mobile"])
                )
            self.send_json({"ok": True, "users": users, "source": "fittrack"})
            return
        if parsed.path.startswith("/api/"):
            self.send_json({"ok": False, "message": "مسیر پیدا نشد."}, HTTPStatus.NOT_FOUND)
            return
        self.serve_static()

    def do_POST(self) -> None:
        if self.reject_unsafe_origin():
            return
        path = urlparse(self.path).path
        if path == "/api/signup":
            if limited(f"signup:{self.client_ip()}", 5, 600):
                self.send_json({"ok": False, "message": "تعداد درخواست‌ها زیاد است؛ کمی بعد دوباره تلاش کنید."}, HTTPStatus.TOO_MANY_REQUESTS, retry_after=600)
                return
            payload = self.read_json()
            if payload is None:
                self.send_json({"ok": False, "message": "اطلاعات ارسال‌شده معتبر نیست."}, HTTPStatus.BAD_REQUEST)
                return
            full_name = re.sub(r"\s+", " ", str(payload.get("fullName", ""))).strip()[:100]
            mobile = normalize_mobile(payload.get("mobile", ""))
            password = str(payload.get("password", ""))
            if len(full_name) < 3:
                self.send_json({"ok": False, "field": "fullName", "message": "نام و نام خانوادگی را کامل وارد کنید."}, HTTPStatus.BAD_REQUEST)
                return
            if not MOBILE_RE.fullmatch(mobile):
                self.send_json({"ok": False, "field": "mobile", "message": "شماره موبایل باید با ۰۹ شروع شود و ۱۱ رقم باشد."}, HTTPStatus.BAD_REQUEST)
                return
            member = fittrack_member(mobile)
            if not member:
                self.send_json(
                    {
                        "ok": False,
                        "field": "mobile",
                        "message": "ابتدا باید عضویت شما در Life Box توسط پذیرش باشگاه ثبت شود.",
                    },
                    HTTPStatus.FORBIDDEN,
                )
                return
            if not password_is_strong(password):
                self.send_json({"ok": False, "field": "password", "message": "رمز عبور باید حداقل ۱۰ کاراکتر و شامل حرف و عدد باشد."}, HTTPStatus.BAD_REQUEST)
                return
            try:
                with connect() as db:
                    fittrack_name = f'{member["first_name"] or ""} {member["last_name"] or ""}'.strip() or full_name
                    cursor = db.execute(
                        """
                        INSERT INTO accounts
                            (full_name, mobile, password_hash, plan, sessions_used, joined_at)
                        VALUES (?, ?, ?, ?, ?, ?)
                        """,
                        (
                            fittrack_name,
                            mobile,
                            hash_password(password),
                            member["plan"] or "عضویت باشگاه",
                            member["used_sessions"] or 0,
                            member["signup_time"] or now_iso(),
                        ),
                    )
                    account_id = cursor.lastrowid
                    account = db.execute("SELECT * FROM accounts WHERE id = ?", (account_id,)).fetchone()
            except sqlite3.IntegrityError:
                self.send_json({"ok": False, "field": "mobile", "message": "با این شماره موبایل قبلاً حساب ساخته شده است."}, HTTPStatus.CONFLICT)
                return
            self.send_json({"ok": True, "user": public_account(account)}, HTTPStatus.CREATED, self.create_session(account_id))
            return

        if path == "/api/login":
            if limited(f"login:{self.client_ip()}", 12, 300):
                self.send_json({"ok": False, "message": "تلاش ورود بیش از حد مجاز است؛ پنج دقیقه بعد دوباره امتحان کنید."}, HTTPStatus.TOO_MANY_REQUESTS, retry_after=300)
                return
            payload = self.read_json()
            if payload is None:
                self.send_json({"ok": False, "message": "اطلاعات ورود معتبر نیست."}, HTTPStatus.BAD_REQUEST)
                return
            mobile = normalize_mobile(payload.get("mobile", ""))
            password = str(payload.get("password", ""))
            with connect() as db:
                account = db.execute("SELECT * FROM accounts WHERE mobile = ?", (mobile,)).fetchone()
                if not account or not verify_password(password, account["password_hash"]):
                    self.send_json({"ok": False, "message": "شماره موبایل یا رمز عبور درست نیست."}, HTTPStatus.UNAUTHORIZED)
                    return
                if account["status"] != "active":
                    self.send_json({"ok": False, "message": "این حساب غیرفعال شده است؛ با مدیریت تماس بگیرید."}, HTTPStatus.FORBIDDEN)
                    return
                db.execute("UPDATE accounts SET last_login_at = ? WHERE id = ?", (now_iso(), account["id"]))
                account = db.execute("SELECT * FROM accounts WHERE id = ?", (account["id"],)).fetchone()
            self.send_json({"ok": True, "user": public_account(account)}, cookie=self.create_session(account["id"]))
            return

        if path == "/api/logout":
            token = self.session_token()
            if token:
                with connect() as db:
                    db.execute("DELETE FROM sessions WHERE token_hash = ?", (hashlib.sha256(token.encode()).hexdigest(),))
            self.send_json({"ok": True}, cookie=self.expired_session_cookie())
            return

        self.send_json({"ok": False, "message": "مسیر پیدا نشد."}, HTTPStatus.NOT_FOUND)

    def do_PATCH(self) -> None:
        if self.reject_unsafe_origin():
            return
        path = unquote(urlparse(self.path).path)
        match = re.fullmatch(r"/api/admin/users/(\d+)/status", path)
        if not match:
            self.send_json({"ok": False, "message": "مسیر پیدا نشد."}, HTTPStatus.NOT_FOUND)
            return
        admin = self.require_account("admin")
        if not admin:
            return
        user_id = int(match.group(1))
        payload = self.read_json()
        new_status = str((payload or {}).get("status", ""))
        if new_status not in {"active", "inactive"}:
            self.send_json({"ok": False, "message": "وضعیت انتخاب‌شده معتبر نیست."}, HTTPStatus.BAD_REQUEST)
            return
        if user_id == admin["id"]:
            self.send_json({"ok": False, "message": "مدیر نمی‌تواند حساب خودش را غیرفعال کند."}, HTTPStatus.BAD_REQUEST)
            return
        with connect() as db:
            cursor = db.execute("UPDATE accounts SET status = ? WHERE id = ?", (new_status, user_id))
            if cursor.rowcount == 0:
                self.send_json({"ok": False, "message": "کاربر پیدا نشد."}, HTTPStatus.NOT_FOUND)
                return
            if new_status == "inactive":
                db.execute("DELETE FROM sessions WHERE account_id = ?", (user_id,))
        self.send_json({"ok": True, "status": new_status})

    def do_OPTIONS(self) -> None:
        self.send_response(HTTPStatus.METHOD_NOT_ALLOWED)
        self.send_header("Allow", "GET, HEAD, POST, PATCH")
        self.end_headers()


def main() -> None:
    init_database()
    server = LifeBoxHTTPServer((HOST, PORT), LifeBoxHandler)
    print(f"LifeBox is ready at http://{HOST}:{PORT}")
    print(f"Environment: {ENVIRONMENT}; HTTPS cookie mode: {USE_HTTPS}")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()


if __name__ == "__main__":
    main()
