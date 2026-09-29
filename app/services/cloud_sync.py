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
                        body = dict(source=self.source, sequence=int(seq[0]) + 1 if seq else 1, records=changes[:100])
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
                    for record in body['records']:
                        key = (record['kind'], record['id'])
                        if record['data'] is None:
                            conn.execute('DELETE FROM sent WHERE kind=? AND id=?', key)
                        else:
                            conn.execute('INSERT OR REPLACE INTO sent VALUES (?,?,?)', (*key, encoded(record['data'])))
                    conn.execute("INSERT OR REPLACE INTO metadata VALUES ('sequence',?)", (str(body['sequence']),))
                    conn.execute('DELETE FROM pending')
                    conn.execute("INSERT OR REPLACE INTO metadata VALUES ('last_success',?)", (datetime.now(timezone.utc).isoformat(),))
                    conn.commit()
                    count += len(body['records'])
                    if not body['records']:
                        # An authenticated heartbeat verifies connectivity even on quiet days.
                        break
            else:
                return count
            if self.workflows:
                for row in self._read(self.state_path, "SELECT application_id,legacy_member_id,paid_amount FROM enrollment_workflows WHERE status='member_created'"):
                    self.api.activate(row['application_id'], row['legacy_member_id'], row['paid_amount'])
                    self.workflows.mark_activated(row['application_id'])
            return count
