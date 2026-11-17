import os
import shutil
import subprocess
from pathlib import Path

from app.core.update_security import file_sha256, validate_version, verify_release, version_tuple
from app.core.version import APP_VERSION
from app.domain.errors import FitTrackError


class UpdateService:
    def __init__(self, api, telemetry, package_root, runtime_root):
        self.api = api
        self.telemetry = telemetry
        self.package_root = Path(package_root).resolve()
        self.runtime_root = Path(runtime_root).resolve()

    @staticmethod
    def validate_release(release):
        required = {'id', 'version', 'notes', 'size', 'sha256', 'signature', 'downloadUrl'}
        if not isinstance(release, dict) or set(release) != required:
            raise FitTrackError("اطلاعات نسخه جدید معتبر نیست.")
        try:
            version = validate_version(release['version'])
            size = int(release['size'])
        except (TypeError, ValueError) as exc:
            raise FitTrackError(str(exc)) from exc
        if version_tuple(version) <= version_tuple(APP_VERSION) or size <= 0 or size > 800 * 1024 * 1024:
            raise FitTrackError("شماره یا حجم نسخه جدید معتبر نیست.")
        return version, size

    def prepare(self, release):
        version, size = self.validate_release(release)
        try:
            self.telemetry.run({"version": version, "status": "downloading", "error": ""})
        except Exception:
            pass
        package = self.runtime_root / "updates" / "downloads" / f"LifeBox-{version}.zip"
        self.api.download_release(release['downloadUrl'], package, size)
        sha256, actual_size = file_sha256(package)
        if sha256.lower() != str(release['sha256']).lower() or actual_size != size:
            package.unlink(missing_ok=True)
            raise FitTrackError("فایل دانلودشده ناقص یا تغییر داده شده است.")
        try:
            verify_release(version, sha256, size, release['signature'])
        except ValueError as exc:
            package.unlink(missing_ok=True)
            raise FitTrackError(str(exc)) from exc
        updater_source = self.package_root / "LifeBoxUpdater.exe"
        if not updater_source.is_file():
            raise FitTrackError("ابزار نصب نسخه جدید در کنار برنامه پیدا نشد.")
        updater = self.runtime_root / "updater" / "LifeBoxUpdater.exe"
        updater.parent.mkdir(parents=True, exist_ok=True)
        temporary = updater.with_suffix(".new")
        shutil.copy2(updater_source, temporary)
        os.replace(temporary, updater)
        return {
            "version": version,
            "package": package,
            "updater": updater,
        }

    def launch(self, prepared):
        version = prepared["version"]
        try:
            self.telemetry.run({"version": version, "status": "installing", "error": ""})
        except Exception:
            pass
        command = [
            str(prepared["updater"]),
            "--package", str(prepared["package"]),
            "--install-dir", str(self.package_root),
            "--runtime-dir", str(self.runtime_root),
            "--pid", str(os.getpid()),
            "--version", version,
        ]
        flags = 0
        if os.name == "nt":
            flags = subprocess.CREATE_NEW_PROCESS_GROUP | subprocess.DETACHED_PROCESS
        subprocess.Popen(
            command,
            cwd=self.runtime_root,
            creationflags=flags,
            close_fds=True,
        )
