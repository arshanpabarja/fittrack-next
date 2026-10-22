from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
import zipfile

import build_desktop_release


class DesktopReleaseTests(unittest.TestCase):
    def test_concurrent_build_is_rejected_and_lock_is_released_after_failure(self):
        with tempfile.TemporaryDirectory() as directory:
            with patch.object(build_desktop_release, "ROOT", Path(directory)):
                with build_desktop_release.exclusive_build():
                    with self.assertRaisesRegex(RuntimeError, "Another desktop build"):
                        with build_desktop_release.exclusive_build():
                            self.fail("Concurrent builds must not enter the build directory")
                with self.assertRaisesRegex(ValueError, "build failure"):
                    with build_desktop_release.exclusive_build():
                        raise ValueError("build failure")
                with build_desktop_release.exclusive_build():
                    pass

    def test_release_includes_binary_and_pos_dll_but_no_owner_or_state(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "Library").mkdir()
            (root / "Library" / "driver.dll").write_bytes(b"test driver")
            (root / ".license-owner").mkdir()
            (root / ".license-owner" / "signing-key.dpapi").write_bytes(b"private")
            (root / "state").mkdir()
            (root / "state" / "activation.lic").write_text("local activation")
            distribution = root / "compiled"
            distribution.mkdir()
            (distribution / "LifeBox.exe").write_bytes(b"compiled binary")
            (distribution / "certifi").mkdir()
            (distribution / "certifi" / "cacert.pem").write_text("public CA bundle")
            (distribution / "codex-rejected-cas.pem").write_text("public CA policy")
            with patch.object(build_desktop_release, "ROOT", root):
                archive = build_desktop_release.package_release(distribution)
            with zipfile.ZipFile(archive) as release:
                self.assertEqual(set(release.namelist()), {
                    "LifeBox/LifeBox.exe", "LifeBox/README.txt", "LifeBox/Library/driver.dll",
                    "LifeBox/certifi/cacert.pem",
                    "LifeBox/codex-rejected-cas.pem",
                })

    def test_unexpected_source_or_secret_aborts_packaging(self):
        for name in ("module.py", "module.pyc", "key.pem", "signing-key.dpapi", "member.db",
                     "state/cloud-config.json", ".license-owner/secret.txt", ".env"):
            with self.subTest(name=name), tempfile.TemporaryDirectory() as directory:
                root = Path(directory)
                (root / "Library").mkdir()
                distribution = root / "compiled"
                distribution.mkdir()
                (distribution / "LifeBox.exe").write_bytes(b"binary")
                secret = distribution / name
                secret.parent.mkdir(parents=True, exist_ok=True)
                secret.write_text("never ship")
                with patch.object(build_desktop_release, "ROOT", root):
                    with self.assertRaises(RuntimeError):
                        build_desktop_release.package_release(distribution)
                self.assertFalse((root / "dist" / "lifebox-desktop.zip").exists())
