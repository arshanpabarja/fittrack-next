import sqlite3
import tempfile
import unittest
from contextlib import closing
from pathlib import Path

from app.data.telemetry import TelemetryRepository
from app.services.telemetry import TelemetryService


class FakeApi:
    def __init__(self):
        self.payload = None

    def telemetry(self, payload):
        self.payload = payload
        return {"ok": True, "release": {"version": "9.0.0", "notes": "test"}}


class TelemetryTests(unittest.TestCase):
    def test_pending_logs_and_heartbeat_are_sent_and_acknowledged(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            state = root / "state.db"
            with closing(sqlite3.connect(state)) as connection:
                connection.execute("CREATE TABLE sample(id INTEGER PRIMARY KEY)")
            queue = root / "cloud_sync.db"
            with closing(sqlite3.connect(queue)) as connection:
                connection.executescript(
                    """
                    CREATE TABLE pending(id INTEGER PRIMARY KEY, body TEXT);
                    CREATE TABLE command_results(id INTEGER PRIMARY KEY, success INTEGER, error TEXT);
                    """
                )
            repository = TelemetryRepository(state)
            repository.append_log("ERROR", "test.logger", "sample failure")
            repository.append_log(
                "ERROR", "test.security", "Authorization: Bearer private-token"
            )
            api = FakeApi()
            service = TelemetryService(api, repository, "gym-a", state, queue)

            response = service.run()

            self.assertEqual(response["release"]["version"], "9.0.0")
            self.assertEqual(api.payload["source"], "gym-a")
            self.assertTrue(api.payload["device"]["databaseOk"])
            self.assertEqual(api.payload["logs"][0]["message"], "sample failure")
            self.assertNotIn("private-token", api.payload["logs"][1]["message"])
            self.assertEqual(repository.pending_logs(), [])
            self.assertEqual(service.latest_release["version"], "9.0.0")


if __name__ == "__main__":
    unittest.main()
