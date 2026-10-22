import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

from app.core.licensing import (
    LicenseError, LicenseStore, PRODUCT, device_id_from_guid, encode_part,
    normalize_device_id, verification_key, verify_license,
)


class LicensingTests(unittest.TestCase):
    def setUp(self):
        self.key = Ed25519PrivateKey.generate()
        self.public = self.key.public_key()
        self.device = device_id_from_guid("machine-one")
        self.claims = {
            "version": 1, "product": PRODUCT, "device": self.device,
            "customer": "باشگاه آزمایشی", "license_id": "example-license",
            "issued_at": "2026-10-12T00:00:00+00:00",
        }

    def token(self, claims=None, key=None):
        payload = json.dumps(self.claims if claims is None else claims).encode()
        signature = (key or self.key).sign(b"LB1." + payload)
        return "LB1." + encode_part(payload) + "." + encode_part(signature)

    def test_valid_license_persists_across_launches_without_new_code(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "state" / "activation.lic"
            store = LicenseStore(path, self.device, self.public)
            self.assertIsNone(store.load())
            self.assertEqual(store.activate(self.token()), self.claims)
            self.assertEqual(LicenseStore(path, self.device, self.public).load(), self.claims)

    def test_copy_to_another_device_is_rejected(self):
        with self.assertRaisesRegex(LicenseError, "دیگری"):
            verify_license(self.token(), device_id_from_guid("machine-two"), self.public)

    def test_edited_payload_with_original_signature_is_rejected(self):
        token = self.token().split(".")
        self.claims["device"] = device_id_from_guid("machine-two")
        token[1] = encode_part(json.dumps(self.claims).encode())
        with self.assertRaises(LicenseError):
            verify_license(".".join(token), self.claims["device"], self.public)

    def test_untrusted_issuer_is_rejected(self):
        with self.assertRaises(LicenseError):
            verify_license(self.token(key=Ed25519PrivateKey.generate()), self.device, self.public)

    def test_wrong_product_version_and_missing_fields_are_rejected(self):
        for updates in ({"product": "another-app"}, {"version": 2}, {"version": True},
                        {"device": "any-machine"}, {"license_id": ""}, {"customer": None}):
            with self.subTest(updates=updates), self.assertRaises(LicenseError):
                verify_license(self.token(dict(self.claims, **updates)), self.device, self.public)

    def test_malformed_and_oversized_codes_are_rejected(self):
        for value in (None, "", "LB1.a.b", "LB2.a.b", "LB1.###.aaa", "a" * 4097,
                      self.token().replace("LB1.", "LB1.=", 1)):
            with self.subTest(value=str(value)[:20]), self.assertRaises(LicenseError):
                verify_license(value, self.device, self.public)

    def test_corrupt_saved_file_cannot_authorize_launch(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "activation.lic"
            path.write_bytes(b"\xff\x00")
            with self.assertRaises(LicenseError):
                LicenseStore(path, self.device, self.public).load()

    def test_bad_activation_does_not_overwrite_valid_license(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "activation.lic"
            store = LicenseStore(path, self.device, self.public)
            store.activate(self.token())
            original = path.read_bytes()
            with self.assertRaises(LicenseError):
                store.activate("wrong code")
            self.assertEqual(path.read_bytes(), original)
            self.assertEqual(store.load(), self.claims)

    def test_failed_save_does_not_report_success_or_leave_temp_file(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "activation.lic"
            store = LicenseStore(path, self.device, self.public)
            with patch("app.core.licensing.os.replace", side_effect=PermissionError):
                with self.assertRaisesRegex(LicenseError, "ذخیره"):
                    store.activate(self.token())
            self.assertFalse(path.exists())
            self.assertEqual(list(Path(directory).iterdir()), [])

    def test_missing_public_key_fails_closed(self):
        with patch("app.core.licensing.PUBLIC_KEY_HEX", ""):
            with self.assertRaises(LicenseError):
                verification_key()

    def test_device_id_is_stable_and_normalized(self):
        self.assertEqual(self.device, device_id_from_guid(" MACHINE-ONE "))
        self.assertEqual(self.device, normalize_device_id(" " + self.device.lower() + " "))
        self.assertNotEqual(self.device, device_id_from_guid("machine-two"))


if __name__ == "__main__":
    unittest.main()
