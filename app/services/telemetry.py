import os
import json
import platform
import shutil
import sqlite3
from contextlib import closing
from pathlib import Path
from threading import RLock

from app.core.version import APP_VERSION


class TelemetryService:
    def __init__(self, api, repository, source, state_path, sync_queue_path):
        self.api = api
        self.repository = repository
        self.source = source
        self.state_path = Path(state_path)
        self.sync_queue_path = Path(sync_queue_path)
        self.runtime_root = self.state_path.parent.parent
        self.update_result_path = self.runtime_root / "update-result.json"
        self._latest_release = None
        self._lock = RLock()
        self._network_lock = RLock()

    @property
    def latest_release(self):
        with self._lock:
            return dict(self._latest_release) if self._latest_release else None

    def _database_status(self):
        try:
            with closing(sqlite3.connect(
                self.state_path.resolve().as_uri() + "?mode=ro", uri=True, timeout=3
            )) as connection:
                result = connection.execute("PRAGMA quick_check(1)").fetchone()
            return result and result[0] == "ok"
        except sqlite3.Error:
            return False

    def _pending_sync(self):
        try:
            with closing(sqlite3.connect(self.sync_queue_path, timeout=3)) as connection:
                pending = connection.execute("SELECT COUNT(*) FROM pending").fetchone()[0]
                results = connection.execute(
                    "SELECT COUNT(*) FROM command_results"
                ).fetchone()[0]
            return int(pending) + int(results)
        except sqlite3.Error:
            return 0

    def heartbeat(self):
        disk = shutil.disk_usage(self.state_path.parent)
        return {
            "appVersion": APP_VERSION,
            "platform": f"{platform.system()} {platform.release()}",
            "stateSize": self.state_path.stat().st_size if self.state_path.exists() else 0,
            "freeDisk": disk.free,
            "databaseOk": self._database_status(),
            "pendingSync": self._pending_sync(),
            "processId": os.getpid(),
        }

    def run(self, update_status=None):
        with self._network_lock:
            return self._run(update_status)

    def _run(self, update_status=None):
        rows = self.repository.pending_logs()
        logs = [
            {
                "id": int(row["id"]),
                "level": row["level"],
                "logger": row["logger"],
                "message": row["message"],
                "occurredAt": row["occurred_at"],
            }
            for row in rows
        ]
        payload = {
            "source": self.source,
            "device": self.heartbeat(),
            "logs": logs,
        }
        result_file = False
        if update_status is None and self.update_result_path.is_file():
            try:
                update_status = json.loads(
                    self.update_result_path.read_text(encoding="utf-8")
                )
                result_file = True
            except (OSError, ValueError, TypeError):
                update_status = None
        if update_status:
            payload["updateStatus"] = dict(update_status)
        response = self.api.telemetry(payload)
        self.repository.mark_sent([row["id"] for row in rows])
        if result_file:
            self.update_result_path.unlink(missing_ok=True)
        with self._lock:
            self._latest_release = response.get("release")
        return response
