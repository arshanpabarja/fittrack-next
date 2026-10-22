import os
from pathlib import Path


# Keep application assets and face models beside this launcher, while sharing
# the live database folder one level above the application directory.
application_root = Path(__file__).resolve().parent
shared_data_dir = Path(os.getenv("FITTRACK_DATA_DIR", application_root.parent / "database")).resolve()
os.environ.setdefault("FITTRACK_ROOT", str(application_root))
os.environ.setdefault("FITTRACK_DATA_DIR", str(shared_data_dir))

from app.bootstrap import run


if __name__ == "__main__":
    raise SystemExit(run())
