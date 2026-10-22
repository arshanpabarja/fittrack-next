import os
import unittest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PyQt6.QtCore import Qt
from PyQt6.QtTest import QTest
from PyQt6.QtWidgets import QApplication

from app.ui.pages.walk_in import KeyboardSpinBox


class WalkInUiTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def test_age_can_be_typed_over_unknown_value(self):
        age = KeyboardSpinBox()
        age.setRange(0, 120)
        age.setSpecialValueText("نامشخص")
        age.show()

        QTest.mouseClick(age.lineEdit(), Qt.MouseButton.LeftButton)
        self.app.processEvents()
        QTest.keyClicks(age, "27")
        self.app.processEvents()

        self.assertEqual(age.value(), 27)
        age.close()


if __name__ == "__main__":
    unittest.main()
