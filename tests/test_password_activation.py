import ast
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from app.core import license_public_key as configuration
from app.core.licensing import LicenseError, LicenseStore, device_id_from_guid, verify_license
from app.core.password_activation import activate_with_password, derive_password_key, public_key_hex
from tools import setup_app_password


class FixedPasswordTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.password = "Owner password 123!"
        cls.salt = bytes(range(16))
        cls.key = derive_password_key(cls.password, cls.salt)

    def setUp(self):
        salt_patch = patch.object(configuration, "PASSWORD_SALT_HEX", self.salt.hex(), create=True)
        public_patch = patch.object(configuration, "PUBLIC_KEY_HEX", public_key_hex(self.key))
        salt_patch.start()
        public_patch.start()
        self.addCleanup(salt_patch.stop)
        self.addCleanup(public_patch.stop)

    def test_same_password_activates_two_devices_but_saved_record_cannot_be_copied(self):
        with tempfile.TemporaryDirectory() as directory:
            first_device = device_id_from_guid("first")
            second_device = device_id_from_guid("second")
            first = LicenseStore(Path(directory) / "first.lic", first_device, self.key.public_key())
            second = LicenseStore(Path(directory) / "second.lic", second_device, self.key.public_key())
            activate_with_password(self.password, first)
            activate_with_password(self.password, second)
            self.assertEqual(first.load()["device"], first_device)
            self.assertEqual(second.load()["device"], second_device)
            with self.assertRaises(LicenseError):
                verify_license(first.path.read_text(), second_device, self.key.public_key())
            # A fresh process/store needs no password again, and stores no password.
            self.assertIsNotNone(LicenseStore(first.path, first_device, self.key.public_key()).load())
            self.assertNotIn(self.password, first.path.read_text())

    def test_wrong_password_does_not_create_activation(self):
        with tempfile.TemporaryDirectory() as directory:
            store = LicenseStore(Path(directory) / "activation.lic", device_id_from_guid("test"), self.key.public_key())
            with self.assertRaisesRegex(LicenseError, "اشتباه"):
                activate_with_password("wrong password", store)
            self.assertFalse(store.path.exists())

    def test_missing_setup_fails_closed(self):
        with patch.object(configuration, "PASSWORD_SALT_HEX", ""):
            with tempfile.TemporaryDirectory() as directory:
                store = LicenseStore(Path(directory) / "activation.lic", device_id_from_guid("test"), self.key.public_key())
                with self.assertRaisesRegex(LicenseError, "تعیین نشده"):
                    activate_with_password(self.password, store)
                self.assertFalse(store.path.exists())

    def test_setup_saves_only_public_verifier_and_preserves_activation_when_password_is_unchanged(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            configuration_path = root / "app/core/license_public_key.py"
            device = device_id_from_guid("test")
            with patch.object(setup_app_password, "ROOT", root):
                with patch.object(setup_app_password, "current_device_id", return_value=device):
                    setup_app_password.set_password(self.password, self.password)
                    first_configuration = configuration_path.read_text()
                    self.assertNotIn(self.password, first_configuration)
                    values = {}
                    for statement in ast.parse(first_configuration).body:
                        if isinstance(statement, ast.Assign):
                            values[statement.targets[0].id] = ast.literal_eval(statement.value)
                    derived = derive_password_key(self.password, bytes.fromhex(values["PASSWORD_SALT_HEX"]))
                    self.assertEqual(public_key_hex(derived), values["PUBLIC_KEY_HEX"])
                    token = (root / ".license-owner/build-check.lic").read_text()
                    self.assertEqual(verify_license(token, device, derived.public_key())["device"], device)
                    setup_app_password.set_password(self.password, self.password)
                    self.assertEqual(configuration_path.read_text(), first_configuration)
                    setup_app_password.set_password("Different password 123", "Different password 123")
                    self.assertNotEqual(configuration_path.read_text(), first_configuration)

    def test_bad_password_setup_leaves_configuration_untouched(self):
        for password, repeat in (("123", "123"), ("Example password", "Different"), ("        ", "        ")):
            with tempfile.TemporaryDirectory() as directory:
                root = Path(directory)
                with patch.object(setup_app_password, "ROOT", root):
                    with self.assertRaises(LicenseError):
                        setup_app_password.set_password(password, repeat)
                self.assertEqual(list(root.iterdir()), [])
