import tempfile
import unittest
import zipfile
from pathlib import Path
from unittest.mock import patch

from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

import desktop_updater
from app.core import update_security
from app.core.update_security import encode_signature, file_sha256, release_manifest
from app.domain.errors import FitTrackError
from app.services.updater import UpdateService


class UpdateTests(unittest.TestCase):
    def test_release_signature_covers_version_hash_and_size(self):
        with tempfile.TemporaryDirectory() as directory:
            package = Path(directory) / "release.zip"
            package.write_bytes(b"signed release content")
            sha256, size = file_sha256(package)
            key = Ed25519PrivateKey.generate()
            public = key.public_key().public_bytes(
                serialization.Encoding.Raw,
                serialization.PublicFormat.Raw,
            ).hex()
            signature = encode_signature(
                key.sign(release_manifest("1.2.0", sha256, size))
            )
            with patch.object(update_security, "PUBLIC_KEY_HEX", public):
                self.assertTrue(
                    update_security.verify_release(
                        "1.2.0", sha256, size, signature
                    )
                )
                with self.assertRaisesRegex(ValueError, "امضای دیجیتال"):
                    update_security.verify_release(
                        "1.2.1", sha256, size, signature
                    )

    def test_client_refuses_downgrade_and_incomplete_metadata(self):
        release = {
            "id": 1,
            "version": "1.0.0",
            "notes": "old",
            "size": 10,
            "sha256": "a" * 64,
            "signature": "LBU1.test",
            "downloadUrl": "https://example.test/release",
        }
        with self.assertRaises(FitTrackError):
            UpdateService.validate_release(release)
        release.pop("notes")
        with self.assertRaises(FitTrackError):
            UpdateService.validate_release(release)

    def test_updater_rejects_zip_path_traversal(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            package = root / "bad.zip"
            target = root / "target"
            target.mkdir()
            with zipfile.ZipFile(package, "w") as archive:
                archive.writestr("../outside.txt", "unsafe")
            with self.assertRaisesRegex(RuntimeError, "ناامن"):
                desktop_updater._safe_extract(package, target)
            self.assertFalse((root / "outside.txt").exists())


if __name__ == "__main__":
    unittest.main()
