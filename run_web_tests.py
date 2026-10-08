"""Run web tests against a temporary file database, including SQLite backup tests."""
import os
from pathlib import Path
import sys
from tempfile import TemporaryDirectory


def main():
    root = Path(__file__).resolve().parent
    sys.path.insert(0, str(root / 'web_portal'))
    os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings')
    import django
    django.setup()
    from django.conf import settings
    from django.db import connections
    from django.test.utils import get_runner

    with TemporaryDirectory(prefix='lifebox-web-tests-') as directory:
        connection = connections['default']
        original_name = connection.settings_dict['TEST']['NAME']
        connection.settings_dict['TEST']['NAME'] = str(Path(directory) / 'test-members.sqlite3')
        try:
            failures = get_runner(settings)(verbosity=1, interactive=False).run_tests(sys.argv[1:] or ['members'])
        finally:
            connections.close_all()
            connection.settings_dict['TEST']['NAME'] = original_name
    return bool(failures)


if __name__ == '__main__':
    sys.exit(main())
