"""Durable, ordered mirroring of gym data. Never uploads biometric material."""
import json
import sqlite3
import threading
from contextlib import closing
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urlsplit

from app.domain.errors import FitTrackError


MEMBER_FIELDS = ('first_name', 'last_name', 'father_name', 'national_id',
                 'certificate_no', 'address', 'mobile', 'age', 'gender', 'plan',
                 'used_sessions', 'signup_time', 'debt', 'payment')


def encoded(value):
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(',', ':'))


class CloudSyncService:
    def __init__(self, api, members_path, state_path, plans, source, workflows=None):
        url = urlsplit(api.base_url)
        if url.scheme != 'https' or not url.hostname or url.username or url.password:
            raise FitTrackError('همگام‌سازی اینترنتی به آدرس HTTPS معتبر نیاز دارد.')
        if len(api.token) < 32 or api.token.startswith('dev-') or not source:
            raise FitTrackError('شناسه باشگاه و توکن امن همگام‌سازی تنظیم نشده است.')
        self.api, self.source, self.plans = api, source, plans
        self.members_path, self.state_path = Path(members_path), Path(state_path)
        self.workflows = workflows
        self.queue_path = self.state_path.with_name('cloud_sync.db')
        self.queue_path.parent.mkdir(parents=True, exist_ok=True)
        self.lock = threading.Lock()
        with closing(sqlite3.connect(self.queue_path)) as conn:
            conn.executescript('''
                CREATE TABLE IF NOT EXISTS metadata (key TEXT PRIMARY KEY, value TEXT NOT NULL);
                CREATE TABLE IF NOT EXISTS sent (kind TEXT, id INTEGER, payload TEXT NOT NULL,
                    PRIMARY KEY(kind,id));
                CREATE TABLE IF NOT EXISTS pending (id INTEGER PRIMARY KEY CHECK(id=1), body TEXT NOT NULL);
                CREATE TABLE IF NOT EXISTS command_results (
                    id INTEGER PRIMARY KEY, success INTEGER NOT NULL, error TEXT NOT NULL
                );
            ''')
            identity = encoded([source, api.base_url, str(self.members_path.resolve()), str(self.state_path.resolve())])
            old = conn.execute("SELECT value FROM metadata WHERE key='identity'").fetchone()
            if old and old[0] != identity:
                raise FitTrackError('مسیر دیتابیس یا مقصد همگام‌سازی تغییر کرده؛ تنظیمات قبلی را بررسی کنید.')
            conn.execute("INSERT OR IGNORE INTO metadata VALUES ('identity',?)", (identity,))
            conn.commit()

    @staticmethod
    def _read(path, sql):
        with closing(sqlite3.connect(path.resolve().as_uri() + '?mode=ro', uri=True, timeout=8)) as conn:
            conn.row_factory = sqlite3.Row
            return [dict(row) for row in conn.execute(sql)]

    def snapshot(self):
        result = {}
        fields = ','.join(MEMBER_FIELDS)
        members = self._read(self.members_path, f'SELECT id,{fields}, '
                             "CASE WHEN embedding IS NOT NULL AND embedding != '' AND length(face_image)>0 "
                             'THEN 1 ELSE 0 END AS face_registered FROM users ORDER BY id')
        for row in members:
            for field in ('used_sessions', 'debt', 'payment'):
                row[field] = int(row[field] or 0)
            row['face_registered'] = bool(row['face_registered'])
            result[('member', row.pop('id'))] = row
        for plan in self.plans.load():
            row = dict(plan.__dict__)
            result[('plan', row.pop('id'))] = row
        for kind, table in [('attendance', 'attendance_sessions'), ('renewal', 'membership_renewals')]:
            for row in self._read(self.state_path, f'SELECT * FROM {table} ORDER BY id'):
                result[(kind, row.pop('id'))] = row
        return result

    def _command_results(self, conn):
        return [dict(id=row[0], success=bool(row[1]), error=row[2])
                for row in conn.execute('SELECT id,success,error FROM command_results ORDER BY id LIMIT 100')]

    def _apply_command(self, command):
        if (not isinstance(command, dict) or set(command) != {'id', 'kind', 'localId', 'data', 'create'} or
                type(command['id']) is not int or type(command['localId']) is not int or
                type(command['create']) is not bool or not isinstance(command['data'], dict)):
            raise FitTrackError('فرمان دریافتی از سایت معتبر نیست.')
        kind, local_id, data = command['kind'], command['localId'], command['data']
        if kind == 'plan':
            expected = {'name', 'price', 'gender', 'sessions_per_month', 'is_active'}
            if set(data) != expected:
                raise FitTrackError('اطلاعات پلن دریافتی معتبر نیست.')
            self.plans.apply_remote(local_id, data, create=command['create'])
            return
        if kind != 'member' or command['create']:
            raise FitTrackError('نوع فرمان دریافتی از سایت پشتیبانی نمی‌شود.')
        allowed = {'first_name', 'last_name', 'mobile', 'national_id', 'address', 'plan', 'debt', 'payment'}
        if not data or not set(data).issubset(allowed):
            raise FitTrackError('اطلاعات عضو دریافتی معتبر نیست.')
        with closing(sqlite3.connect(self.members_path, timeout=15)) as members:
            members.row_factory = sqlite3.Row
            current = members.execute('SELECT * FROM users WHERE id=?', (local_id,)).fetchone()
            if not current:
                raise FitTrackError('عضو موردنظر در برنامه باشگاه پیدا نشد.')
            mobile = data.get('mobile')
            national_id = data.get('national_id')
            if mobile and members.execute('SELECT 1 FROM users WHERE mobile=? AND id!=?', (mobile, local_id)).fetchone():
                raise FitTrackError('شماره موبایل در برنامه باشگاه تکراری است.')
            if national_id and members.execute('SELECT 1 FROM users WHERE national_id=? AND id!=?', (national_id, local_id)).fetchone():
                raise FitTrackError('کد ملی در برنامه باشگاه تکراری است.')
            if mobile and mobile != current['mobile']:
                with closing(sqlite3.connect(self.state_path.resolve().as_uri() + '?mode=ro', uri=True, timeout=8)) as state:
                    if state.execute('SELECT 1 FROM attendance_sessions WHERE member_id=? AND checked_out_at IS NULL', (local_id,)).fetchone():
                        raise FitTrackError('ابتدا خروج این عضو از باشگاه ثبت شود.')
            if 'plan' in data and not any(plan.name == data['plan'] and plan.is_active for plan in self.plans.load()):
                raise FitTrackError('پلن انتخاب‌شده در فهرست فعال باشگاه پیدا نشد.')
            assignments = ','.join(f'{field}=?' for field in data)
            members.execute(f'UPDATE users SET {assignments} WHERE id=?', (*data.values(), local_id))
            members.commit()

    def _store_command_results(self, commands):
        for command in commands:
            try:
                self._apply_command(command)
                success, message = 1, ''
            except Exception as exc:
                success, message = 0, str(exc)[:500] or 'اعمال تغییر در برنامه باشگاه ناموفق بود.'
            with closing(sqlite3.connect(self.queue_path, timeout=15)) as conn:
                conn.execute('INSERT OR REPLACE INTO command_results VALUES (?,?,?)',
                             (command.get('id', 0), success, message))
                conn.commit()

    def run(self):
        # Serializes UI enrollment and timer work; SQLite also serializes separate processes.
        with self.lock:
            count = 0
            for _ in range(20):  # Bound each worker run; the next tick continues large imports.
                with closing(sqlite3.connect(self.queue_path, timeout=15)) as conn:
                    conn.execute('BEGIN IMMEDIATE')
                    pending = conn.execute('SELECT body FROM pending WHERE id=1').fetchone()
                    if pending:
                        body = json.loads(pending[0])
                    else:
                        current = self.snapshot()
                        previous = {(k, i): p for k, i, p in conn.execute('SELECT kind,id,payload FROM sent')}
                        changes = [dict(kind=k, id=i, data=data) for (k, i), data in current.items()
                                   if previous.get((k, i)) != encoded(data)]
                        # Only remove rows previously acknowledged from this exact database.
                        changes += [dict(kind=k, id=i, data=None) for k, i in previous if (k, i) not in current]
                        seq = conn.execute("SELECT value FROM metadata WHERE key='sequence'").fetchone()
                        body = dict(source=self.source, sequence=int(seq[0]) + 1 if seq else 1,
                                    records=changes[:100], commandResults=self._command_results(conn))
                        conn.execute('INSERT INTO pending VALUES (1,?)', (encoded(body),))
                        conn.commit()  # Persist before touching the network, including on abrupt shutdown.
                        conn.execute('BEGIN IMMEDIATE')
                        pending = conn.execute('SELECT body FROM pending WHERE id=1').fetchone()
                        if not pending:  # Another process completed this batch.
                            conn.commit()
                            continue
                        body = json.loads(pending[0])
                    response = self.api._request('POST', '/api/desktop/sync', body)
                    if response.get('sequence') != body['sequence']:
                        raise FitTrackError('تأیید همگام‌سازی سایت معتبر نیست.')
                    commands = response.get('commands', [])
                    result_acks = response.get('resultAcks', [])
                    if not isinstance(commands, list) or not isinstance(result_acks, list) or any(type(value) is not int for value in result_acks):
                        raise FitTrackError('پاسخ فرمان‌های سایت معتبر نیست.')
                    for record in body['records']:
                        key = (record['kind'], record['id'])
                        if record['data'] is None:
                            conn.execute('DELETE FROM sent WHERE kind=? AND id=?', key)
                        else:
                            conn.execute('INSERT OR REPLACE INTO sent VALUES (?,?,?)', (*key, encoded(record['data'])))
                    conn.execute("INSERT OR REPLACE INTO metadata VALUES ('sequence',?)", (str(body['sequence']),))
                    conn.execute('DELETE FROM pending')
                    for command_id in result_acks:
                        conn.execute('DELETE FROM command_results WHERE id=?', (command_id,))
                    conn.execute("INSERT OR REPLACE INTO metadata VALUES ('last_success',?)", (datetime.now(timezone.utc).isoformat(),))
                    conn.commit()
                    self._store_command_results(commands)
                    count += len(body['records'])
                    if not body['records'] and not commands and not body['commandResults']:
                        # An authenticated heartbeat verifies connectivity even on quiet days.
                        break
            else:
                return count
            if self.workflows:
                for row in self._read(self.state_path, "SELECT application_id,legacy_member_id,paid_amount FROM enrollment_workflows WHERE status='member_created'"):
                    self.api.activate(row['application_id'], row['legacy_member_id'], row['paid_amount'])
                    self.workflows.mark_activated(row['application_id'])
            return count
