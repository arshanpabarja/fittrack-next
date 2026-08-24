"""Launcher for a Desktop copy that keeps the live database shared."""

import os
from pathlib import Path


desktop = Path(__file__).resolve().parent.parent
live_project = desktop / "FitTrack"
if not live_project.is_dir():
    raise RuntimeError(f"Life Box data folder was not found: {live_project}")

os.environ.setdefault("FITTRACK_ROOT", str(live_project))

from app.bootstrap import run


if __name__ == "__main__":
    raise SystemExit(run())
