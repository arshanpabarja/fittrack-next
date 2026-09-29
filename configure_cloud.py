"""Run once on the gym computer; secrets are kept in ignored state/, never in Git."""
import getpass
import json
import os
import sqlite3
from contextlib import closing
from datetime import datetime
from pathlib import Path
from urllib.parse import urlsplit
from uuid import UUID


def main():
    root = Path(__file__).resolve().parent
    url = input('Website URL [https://lifeboxgym.com]: ').strip().rstrip('/') or 'https://lifeboxgym.com'
    parts = urlsplit(url)
    if parts.scheme != 'https' or not parts.hostname or parts.username or parts.password or parts.path or parts.query or parts.fragment:
        raise SystemExit('Enter only an HTTPS origin, e.g. https://lifeboxgym.com')
    source = str(UUID(input('FITTRACK_SYNC_SOURCE from server: ').strip()))
    token = getpass.getpass('FITTRACK_DESKTOP_API_TOKEN from server (hidden): ').strip()
    if len(token) < 32 or token.startswith('dev-'):
        raise SystemExit('Use a randomly generated token of at least 32 characters.')
    path = root / 'state' / 'cloud-config.json'
    if path.exists():
        raise SystemExit('Configuration already exists. Review state/cloud-config.json; do not reset cloud_sync.db.')
    data_dir = Path(os.environ.get('FITTRACK_DATA_DIR', root.parent / 'database'))
    if not (data_dir / 'gym_users.db').is_file() or not (data_dir / 'plans.json').is_file():
        raise SystemExit('Gym database or plans.json not found. Set FITTRACK_DATA_DIR to the live database directory.')
    backup_dir = root / 'backups' / ('before-cloud-' + datetime.now().strftime('%Y%m%d-%H%M%S'))
    backup_dir.mkdir(parents=True, exist_ok=False)
    for database in (data_dir / 'gym_users.db', root / 'state' / 'fittrack_next.db'):
        if database.is_file():
            with closing(sqlite3.connect(database.resolve().as_uri() + '?mode=ro', uri=True)) as source_db:
                with closing(sqlite3.connect(backup_dir / database.name)) as target_db:
                    source_db.backup(target_db)
    (backup_dir / 'plans.json').write_bytes((data_dir / 'plans.json').read_bytes())
    # Stabilize legacy plan IDs before the first upload, without changing plan contents.
    from app.services.plans import PlansService
    plans = PlansService(None, data_dir / 'plans.json')
    plans._write_local(plans.load())
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open('x', encoding='utf-8') as stream:
        json.dump(dict(FITTRACK_API_URL=url, FITTRACK_SYNC_SOURCE=source,
                       FITTRACK_DESKTOP_API_TOKEN=token, FITTRACK_CLOUD_SYNC='1'), stream, indent=2)
    print('Configured. Restart Life Box. Sync status appears at the bottom of the window.')


if __name__ == '__main__':
    main()
