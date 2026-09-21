from dataclasses import dataclass
import os
from pathlib import Path


@dataclass(frozen=True)
class Settings:
    project_root: Path
    data_dir: Path
    assets_dir: Path
    log_dir: Path
    django_base_url: str
    desktop_api_token: str
    pos_mode: str

    @property
    def members_database(self):
        return self.data_dir / "gym_users.db"

    @property
    def attendance_database(self):
        return self.data_dir / "gym_checkInOut.db"

    @property
    def single_session_database(self):
        return self.data_dir / "gym_SingleSession.db"

    @property
    def manager_database(self):
        return self.data_dir / "gym_manager.db"

    @property
    def state_database(self):
        return self.log_dir.parent / "state" / "fittrack_next.db"


def load_settings():
    package_root = Path(__file__).resolve().parents[2]
    root = Path(os.getenv("FITTRACK_ROOT", package_root)).resolve()
    data_dir = Path(os.getenv("FITTRACK_DATA_DIR", root / "database")).resolve()
    return Settings(
        project_root=root,
        data_dir=data_dir,
        assets_dir=root / "assets",
        log_dir=package_root / "logs",
        django_base_url=os.getenv(
            "FITTRACK_API_URL", "http://192.168.100.95:8000"
        ).rstrip("/"),
        desktop_api_token=os.getenv(
            "FITTRACK_DESKTOP_API_TOKEN",
            "dev-fittrack-desktop-token-change-before-public",
        ),
        pos_mode=os.getenv("FITTRACK_POS_MODE", "real").strip().lower(),
    )
