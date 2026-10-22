from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import (
    QDialog, QHBoxLayout, QLabel, QLineEdit,
    QMessageBox, QPushButton, QVBoxLayout,
)

from app.core.licensing import LicenseError, LicenseStore, current_device_id
from app.core.password_activation import activate_with_password, password_configuration


class ActivationDialog(QDialog):
    def __init__(self, store, initial_error=""):
        super().__init__()
        self.store = store
        self.setWindowTitle("ورود اولیه به لایف‌باکس")
        self.setLayoutDirection(Qt.LayoutDirection.RightToLeft)
        self.setMinimumWidth(460)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(28, 28, 28, 28)
        layout.setSpacing(14)
        title = QLabel("رمز ورود به برنامه")
        title.setObjectName("loginTitle")
        layout.addWidget(title)
        description = QLabel(
            "رمزی را که از صاحب برنامه گرفته‌اید وارد کنید.\n"
            "فقط بار اول روی این سیستم رمز پرسیده می‌شود."
        )
        description.setWordWrap(True)
        layout.addWidget(description)
        self.password = QLineEdit()
        self.password.setMaxLength(256)
        self.password.setPlaceholderText("رمز برنامه")
        self.password.setEchoMode(QLineEdit.EchoMode.Password)
        self.password.returnPressed.connect(self.submit)
        layout.addWidget(self.password)
        self.error = QLabel(initial_error)
        self.error.setObjectName("formError")
        self.error.setWordWrap(True)
        self.error.setVisible(bool(initial_error))
        layout.addWidget(self.error)
        buttons = QHBoxLayout()
        activate = QPushButton("ورود به برنامه")
        activate.clicked.connect(self.submit)
        cancel = QPushButton("خروج")
        cancel.setObjectName("secondaryButton")
        cancel.clicked.connect(self.reject)
        buttons.addWidget(activate)
        buttons.addWidget(cancel)
        layout.addLayout(buttons)
        self.password.setFocus()

    def submit(self):
        try:
            activate_with_password(self.password.text(), self.store)
        except LicenseError as exc:
            self.error.setText(str(exc))
            self.error.show()
            self.password.selectAll()
            self.password.setFocus()
            return
        self.password.clear()
        self.accept()


def ensure_activation(root):
    try:
        password_configuration()
        store = LicenseStore(root / "state" / "activation.lic", current_device_id())
    except LicenseError as exc:
        QMessageBox.critical(None, "فعال‌سازی لایف‌باکس", str(exc))
        return False
    error = ""
    try:
        if store.load() is not None:
            return True
    except LicenseError:
        error = "برای ورود اولیه به این نسخه، رمز برنامه را وارد کنید."
    return ActivationDialog(store, error).exec() == QDialog.DialogCode.Accepted
