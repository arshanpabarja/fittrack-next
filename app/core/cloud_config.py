import json
import os
from pathlib import Path


def load_cloud_config(root):
    """A machine-local file survives shortcut launches; environment takes precedence."""
    path = Path(root) / 'state' / 'cloud-config.json'
    if not path.exists():
        return
    values = json.loads(path.read_text(encoding='utf-8'))
    for key in ('FITTRACK_API_URL', 'FITTRACK_DESKTOP_API_TOKEN', 'FITTRACK_SYNC_SOURCE', 'FITTRACK_CLOUD_SYNC'):
        if key in values:
            os.environ.setdefault(key, str(values[key]))
