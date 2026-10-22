from PyQt6.QtCore import QProcess, Qt
from PyQt6.QtGui import QFont, QFontDatabase
from PyQt6.QtWidgets import (
    QApplication, QDialog, QLabel, QLineEdit, QPlainTextEdit, QPushButton, QVBoxLayout,
)

from app.core.licensing import LicenseError
from tools.setup_app_password import ROOT, set_password


class PasswordSetupDialog(QDialog):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("تعیین رمز اصلی لایف‌باکس — مخصوص صاحب برنامه")
        self.setLayoutDirection(Qt.LayoutDirection.RightToLeft)
        self.setMinimumWidth(560)
        self.process = None
        self.busy = False
        self.configured = False
        layout = QVBoxLayout(self)
        layout.setContentsMargins(28, 28, 28, 28)
        layout.setSpacing(14)
        description = QLabel(
            "یک رمز ثابت برای برنامه انتخاب کنید؛ همین رمز روی همهٔ سیستم‌ها استفاده می‌شود.\n"
            "هر سیستم فقط بار اول رمز را می‌پرسد. رمز را در جای امن نگه دارید."
        )
        description.setWordWrap(True)
        layout.addWidget(description)
        self.password = QLineEdit()
        self.password.setEchoMode(QLineEdit.EchoMode.Password)
        self.password.setMaxLength(256)
        self.password.setPlaceholderText("رمز دلخواه شما — حداقل ۸ نویسه")
        self.confirmation = QLineEdit()
        self.confirmation.setEchoMode(QLineEdit.EchoMode.Password)
        self.confirmation.setMaxLength(256)
        self.confirmation.setPlaceholderText("تکرار همان رمز")
        layout.addWidget(self.password)
        layout.addWidget(self.confirmation)
        self.status = QLabel("")
        self.status.setWordWrap(True)
        layout.addWidget(self.status)
        self.save = QPushButton("ثبت رمز و ساخت نسخهٔ آمادهٔ تحویل")
        self.save.clicked.connect(self.submit)
        layout.addWidget(self.save)
        self.output = QPlainTextEdit()
        self.output.setReadOnly(True)
        self.output.setLayoutDirection(Qt.LayoutDirection.LeftToRight)
        self.output.setMaximumBlockCount(100)
        self.output.hide()
        layout.addWidget(self.output)
        self.confirmation.returnPressed.connect(self.submit)

    def submit(self):
        if self.busy:
            return
        if not self.configured:
            try:
                set_password(self.password.text(), self.confirmation.text())
            except (LicenseError, OSError) as exc:
                self.status.setText(str(exc))
                return
            self.configured = True
            self.password.clear()
            self.confirmation.clear()
        self.busy = True
        self.save.setEnabled(False)
        self.password.setEnabled(False)
        self.confirmation.setEnabled(False)
        self.status.setText("رمز ثبت شد. در حال ساخت نسخهٔ اجرایی؛ این پنجره را باز نگه دارید…")
        self.output.show()
        self.process = QProcess(self)
        self.process.setWorkingDirectory(str(ROOT))
        self.process.setProcessChannelMode(QProcess.ProcessChannelMode.MergedChannels)
        self.process.readyReadStandardOutput.connect(self.read_output)
        self.process.errorOccurred.connect(self.build_error)
        self.process.finished.connect(self.build_finished)
        self.process.start(str(ROOT / ".venv" / "Scripts" / "python.exe"), [str(ROOT / "build_desktop_release.py")])

    def read_output(self):
        self.output.appendPlainText(bytes(self.process.readAllStandardOutput()).decode("utf-8", errors="replace").strip())

    def build_error(self, error):
        self.status.setText("رمز ثبت شد، ولی اجرای ابزار ساخت ناموفق بود. جزئیات پایین پنجره را بررسی کنید.")
        self.busy = False
        self.save.setEnabled(True)
        self.save.setText("تلاش دوباره برای ساخت بسته")

    def build_finished(self, code, status):
        self.busy = False
        if code == 0 and status == QProcess.ExitStatus.NormalExit:
            self.status.setText("تمام شد. بستهٔ آمادهٔ مشتری: dist/lifebox-desktop.zip")
        else:
            self.status.setText("رمز ثبت شد، ولی ساخت بسته تمام نشد؛ خطای پایین پنجره را بررسی کنید.")
            self.save.setEnabled(True)
            self.save.setText("تلاش دوباره برای ساخت بسته")

    def closeEvent(self, event):
        if self.busy:
            self.status.setText("ساخت نسخه در حال انجام است؛ لطفاً تا پایان این پنجره را باز نگه دارید.")
            event.ignore()
        else:
            event.accept()


def run():
    app = QApplication.instance() or QApplication([])
    font_id = QFontDatabase.addApplicationFont(str(ROOT / "Vazirmatn-Bold.ttf"))
    families = QFontDatabase.applicationFontFamilies(font_id)
    if families:
        app.setFont(QFont(families[0], 10))
    app.setStyleSheet((ROOT / "app/ui/theme.qss").read_text(encoding="utf-8"))
    PasswordSetupDialog().exec()
    return 0
