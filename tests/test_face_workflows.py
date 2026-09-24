import os
import unittest
from pathlib import Path
from unittest.mock import Mock, patch

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
from PyQt6.QtWidgets import QApplication

from app.integrations.camera import CameraWorker
from app.ui.pages.walk_in import WalkInSignupPage


class FaceWorkflowTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def test_countdown_starts_with_preview_and_never_captures_early(self):
        worker = CameraWorker(Path("models"), auto_capture=True, capture_delay=4)
        messages = []
        worker.status_changed.connect(messages.append)
        self.assertFalse(worker._capture_ready(100))
        self.assertFalse(worker._capture_ready(103.9))
        self.assertTrue(worker._capture_ready(104))
        self.assertTrue(worker._capture_ready(105))
        self.assertEqual(len(messages), 3)

    def test_retry_is_available_after_cancel_and_enables_payment_after_capture(self):
        page = WalkInSignupPage(Mock(), Mock(), Path("models"), (0,))
        page.stack.setCurrentIndex(2)
        with patch("app.ui.pages.walk_in.FaceCaptureDialog") as dialog:
            page._capture_face()
            self.assertEqual(dialog.call_args.kwargs["capture_delay"], 4)
            self.assertTrue(page.rescan_button.isEnabled())
            self.assertFalse(page.register_button.isEnabled())
            dialog.return_value.exec.side_effect = lambda: page._face_captured([1, 0], b"face")
            page._capture_face()
            self.assertTrue(page.register_button.isEnabled())
            self.assertEqual(page.face_image, b"face")
            page.busy = True
            page._capture_face()
            self.assertEqual(dialog.call_count, 2)
        page.close()
