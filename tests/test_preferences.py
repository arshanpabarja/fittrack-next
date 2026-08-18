import tempfile
import unittest
from pathlib import Path

from app.data.preferences import PreferencesRepository
from app.domain.errors import ValidationError
from app.services.preferences import PreferencesService


class PreferencesTests(unittest.TestCase):
    def test_preferences_are_validated_and_persisted(self):
        with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as directory:
            service = PreferencesService(
                PreferencesRepository(Path(directory) / "state.db")
            )
            values = service.save({
                "api_url": "http://192.168.100.95:8000/",
                "camera_indices": "0, 2",
                "face_threshold": "0.55",
            })
            self.assertEqual(values["api_url"], "http://192.168.100.95:8000")
            self.assertEqual(values["camera_indices"], "0,2")
            self.assertEqual(values["face_threshold"], "0.55")

    def test_invalid_threshold_is_rejected(self):
        with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as directory:
            service = PreferencesService(
                PreferencesRepository(Path(directory) / "state.db")
            )
            with self.assertRaises(ValidationError):
                service.save({
                    "api_url": "http://localhost:8000",
                    "camera_indices": "0",
                    "face_threshold": "1.5",
                })


if __name__ == "__main__":
    unittest.main()

