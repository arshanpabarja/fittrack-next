import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import Mock, patch

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PyQt6.QtWidgets import QApplication, QDialog

from app.core.licensing import LicenseError, LicenseStore, device_id_from_guid
from app.core import license_public_key as configuration
from app.core.password_activation import derive_password_key, public_key_hex
from app.ui.activation import ActivationDialog, ensure_activation


class ActivationUiTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])
        cls.test_password = "Test password 123!"
        cls.test_salt = bytes(range(16))
        cls.test_key = derive_password_key(cls.test_password, cls.test_salt)

    def setUp(self):
        self.salt_patch = patch.object(configuration, "PASSWORD_SALT_HEX", self.test_salt.hex(), create=True)
        self.public_patch = patch.object(configuration, "PUBLIC_KEY_HEX", public_key_hex(self.test_key))
        self.salt_patch.start()
        self.public_patch.start()
        self.addCleanup(self.salt_patch.stop)
        self.addCleanup(self.public_patch.stop)

    def test_wrong_password_stays_locked_and_correct_password_accepts_and_saves(self):
        device = device_id_from_guid("ui-test-machine")
        with tempfile.TemporaryDirectory() as directory:
            store = LicenseStore(Path(directory) / "activation.lic", device, self.test_key.public_key())
            dialog = ActivationDialog(store)
            dialog.password.setText("incorrect")
            dialog.submit()
            self.assertEqual(dialog.result(), QDialog.DialogCode.Rejected)
            self.assertTrue(dialog.error.text())
            self.assertFalse(store.path.exists())
            dialog.password.setText(self.test_password)
            dialog.submit()
            self.assertEqual(dialog.result(), QDialog.DialogCode.Accepted)
            self.assertEqual(store.load()["device"], device)
            self.assertEqual(dialog.password.text(), "")

    def test_saved_license_skips_activation_dialog(self):
        store = Mock()
        store.load.return_value = {"license_id": "valid"}
        with patch("app.ui.activation.current_device_id", return_value="device"):
            with patch("app.ui.activation.LicenseStore", return_value=store):
                with patch("app.ui.activation.ActivationDialog") as dialog:
                    self.assertTrue(ensure_activation(Path("test")))
                    dialog.assert_not_called()

    def test_missing_or_tampered_license_requires_dialog_and_cancel_denies_access(self):
        for failure in (None, LicenseError("tampered")):
            with self.subTest(failure=failure):
                store = Mock()
                store.load.return_value = None
                if failure is not None:
                    store.load.side_effect = failure
                with patch("app.ui.activation.current_device_id", return_value="device"):
                    with patch("app.ui.activation.LicenseStore", return_value=store):
                        with patch("app.ui.activation.ActivationDialog") as dialog:
                            dialog.return_value.exec.return_value = QDialog.DialogCode.Rejected
                            self.assertFalse(ensure_activation(Path("test")))
                            dialog.assert_called_once()

    def test_unreadable_machine_identity_denies_access(self):
        with patch("app.ui.activation.current_device_id", side_effect=LicenseError("no identity")):
            with patch("app.ui.activation.QMessageBox.critical"):
                with patch("app.ui.activation.ActivationDialog") as dialog:
                    self.assertFalse(ensure_activation(Path("test")))
                    dialog.assert_not_called()

    def test_startup_denial_prevents_settings_and_business_services(self):
        from app import bootstrap
        with patch.object(bootstrap, "QApplication", return_value=self.app):
            with patch.object(bootstrap, "ensure_activation", return_value=False):
                with patch.object(bootstrap, "load_settings") as settings:
                    with patch.object(bootstrap, "build_services") as services:
                        with patch.object(bootstrap, "MainWindow") as window:
                            self.assertEqual(bootstrap.run(), 1)
                            settings.assert_not_called()
                            services.assert_not_called()
                            window.assert_not_called()

    def test_password_setup_validation_prevents_build_on_mismatched_password(self):
        from tools.setup_app_password_ui import PasswordSetupDialog
        dialog = PasswordSetupDialog()
        dialog.password.setText("Example password")
        dialog.confirmation.setText("Different password")
        with patch("tools.setup_app_password_ui.QProcess") as process:
            dialog.submit()
            process.assert_not_called()
        self.assertTrue(dialog.status.text())
        self.assertFalse(dialog.configured)

    def test_password_setup_clears_secret_and_retries_build_without_resetting_password(self):
        from tools.setup_app_password_ui import PasswordSetupDialog
        from PyQt6.QtCore import QProcess
        dialog = PasswordSetupDialog()
        dialog.password.setText("Example password")
        dialog.confirmation.setText("Example password")
        with patch("tools.setup_app_password_ui.set_password") as save:
            with patch("tools.setup_app_password_ui.QProcess") as process:
                dialog.submit()
                self.assertTrue(dialog.configured)
                self.assertEqual(dialog.password.text(), "")
                self.assertEqual(dialog.confirmation.text(), "")
                self.assertTrue(process.return_value.start.called)
                dialog.build_finished(1, QProcess.ExitStatus.NormalExit)
                dialog.submit()
                save.assert_called_once()


if __name__ == "__main__":
    unittest.main()
