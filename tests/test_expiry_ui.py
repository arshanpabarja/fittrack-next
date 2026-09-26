import os
import unittest
from pathlib import Path
from unittest.mock import Mock, patch

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
from PyQt6.QtWidgets import QApplication, QLabel
from app.domain.errors import MembershipExpired
from app.ui.pages.attendance import AttendancePage, MemberInfoDialog
from app.ui.workers import TaskWorker
from tests.test_membership_expiry import ExpiryTests


class ExpiryUiTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def test_expired_error_opens_renewal_for_the_identified_member(self):
        page = AttendancePage(Mock(), Mock(), Path('models'), (0,))
        page._load_renewal = Mock()
        with patch('app.ui.pages.attendance.QMessageBox') as box:
            renew = object()
            box.return_value.addButton.side_effect = [renew, object()]
            box.return_value.clickedButton.return_value = renew
            page._operation_failed(MembershipExpired(42))
        page._load_renewal.assert_called_once_with(42)

    def test_worker_preserves_expired_member_id(self):
        error = MembershipExpired(42)
        worker = TaskWorker(Mock(side_effect=error))
        received = []
        worker.signals.failed_exception.connect(received.append)
        with patch('app.ui.workers.logging'):
            worker.run()
        self.assertEqual(received, [error])

    @patch('app.domain.dates.jalali_now', return_value='1405-07-01 10:00:00')
    def test_expired_details_show_expiry_instead_of_unused_sessions(self, clock):
        dialog = MemberInfoDialog(ExpiryTests().member(2))
        labels = [label.text() for label in dialog.findChildren(QLabel)]
        self.assertIn('مهلت استفاده تمام شده', labels)
        self.assertNotIn('10', labels)
