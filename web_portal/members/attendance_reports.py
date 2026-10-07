"""Read attendance from the configured source, filtering before pagination."""
import sqlite3
from contextlib import closing

from django.conf import settings
from django.db.models import Q

from .models import GymSyncCursor, GymSyncRecord
from .views import normalize_digits


def search_terms(value):
    return str(value or '').strip()[:100].split()


def attendance_report(start, end, *, search='', member_id=None, page=1, page_size=500):
    result = dict(attendance=[], attendanceAvailable=False, syncedAt=None,
                  visitCount=0, visitors=0, inside=0, page=page, pageSize=page_size)
    offset = (page - 1) * page_size
    if settings.FITTRACK_REMOTE_SYNC:
        rows = GymSyncRecord.objects.filter(kind='attendance')
        visits = rows.filter(data__checked_in_at__gte=start.isoformat(),
                             data__checked_in_at__lt=end.isoformat())
        if member_id is not None:
            visits = visits.filter(data__member_id=member_id)
        for term in search_terms(search):
            visits = visits.filter(Q(data__full_name__icontains=term) |
                                   Q(data__mobile__icontains=normalize_digits(term)))
        cursor = GymSyncCursor.objects.first()
        available = bool(cursor and cursor.sequence)
        result.update(attendanceAvailable=available,
                      syncedAt=cursor.updated_at.isoformat() if available else None,
                      visitCount=visits.count(),
                      visitors=visits.values('data__member_id').distinct().count(),
                      inside=rows.filter(data__checked_out_at=None).count(),
                      attendance=list(visits.order_by('-data__checked_in_at', '-local_id')
                                      .values_list('data', flat=True)[offset:offset + page_size]))
    else:
        clauses = ['checked_in_at>=?', 'checked_in_at<?']
        params = [start.isoformat(), end.isoformat()]
        if member_id is not None:
            clauses.append('member_id=?')
            params.append(member_id)
        for term in search_terms(search):
            # Escape LIKE wildcards so a name/phone query remains literal.
            escape = lambda value: value.replace('\\', '\\\\').replace('%', '\\%').replace('_', '\\_')
            clauses.append("(full_name LIKE ? ESCAPE '\\' OR mobile LIKE ? ESCAPE '\\')")
            params.extend([f'%{escape(term)}%', f'%{escape(normalize_digits(term))}%'])
        where = ' AND '.join(clauses)
        try:
            path = settings.FITTRACK_ATTENDANCE_PATH.resolve().as_uri() + '?mode=ro'
            with closing(sqlite3.connect(path, uri=True, timeout=5)) as conn:
                conn.row_factory = sqlite3.Row
                count, unique = conn.execute(
                    f'SELECT COUNT(*), COUNT(DISTINCT member_id) FROM attendance_sessions WHERE {where}', params
                ).fetchone()
                inside = conn.execute('SELECT COUNT(*) FROM attendance_sessions WHERE checked_out_at IS NULL').fetchone()[0]
                attendance = [dict(row) for row in conn.execute(
                    'SELECT member_id,full_name,mobile,plan,checked_in_at,checked_out_at,locker_id '
                    f'FROM attendance_sessions WHERE {where} ORDER BY checked_in_at DESC, rowid DESC LIMIT ? OFFSET ?',
                    [*params, page_size, offset],
                )]
            result.update(attendance=attendance, attendanceAvailable=True,
                          visitCount=count, visitors=unique, inside=inside)
        except (sqlite3.Error, OSError):
            pass
    result['hasNext'] = offset + page_size < result['visitCount']
    return result
