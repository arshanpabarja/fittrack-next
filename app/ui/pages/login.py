from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtWidgets import (
    QFrame,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from app.domain.errors import FitTrackError


class ManagerLoginPage(QWidget):
    authenticated = pyqtSignal(str)
    cancelled = pyqtSignal()

    def __init__(self, service):
        super().__init__()
        self.service = service
        layout = QVBoxLayout(self)
        layout.setAlignment(Qt.AlignmentFlag.AlignCenter)

        card = QFrame()
        card.setObjectName("loginCard")
        card.setFixedWidth(440)
        form = QVBoxLayout(card)
        form.setContentsMargins(38, 34, 38, 34)
        form.setSpacing(14)
        title = QLabel("ورود مدیر")
        title.setObjectName("loginTitle")
        title.setAlignment(Qt.AlignmentFlag.AlignCenter)
        subtitle = QLabel("برای دسترسی به اطلاعات مدیریتی وارد شوید.")
        subtitle.setObjectName("pageSubtitle")
        subtitle.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.username = QLineEdit()
        self.username.setPlaceholderText("نام کاربری")
        self.username.setClearButtonEnabled(True)
        self.password = QLineEdit()
        self.password.setPlaceholderText("رمز عبور")
        self.password.setEchoMode(QLineEdit.EchoMode.Password)
        self.password.returnPressed.connect(self.submit)
        self.error = QLabel("")
        self.error.setObjectName("formError")
        self.error.setWordWrap(True)
        self.error.hide()
        submit = QPushButton("ورود")
        submit.clicked.connect(self.submit)
        cancel = QPushButton("بازگشت")
        cancel.setObjectName("secondaryButton")
        cancel.clicked.connect(self.cancelled.emit)
        buttons = QHBoxLayout()
        buttons.addWidget(submit)
        buttons.addWidget(cancel)
        form.addWidget(title)
        form.addWidget(subtitle)
        form.addSpacing(8)
        form.addWidget(self.username)
        form.addWidget(self.password)
        form.addWidget(self.error)
        form.addLayout(buttons)
        layout.addWidget(card)

    def prepare(self):
        self.password.clear()
        self.error.hide()
        self.username.setFocus()

    def submit(self):
        try:
            username = self.service.login(self.username.text(), self.password.text())
        except FitTrackError as exc:
            self.error.setText(str(exc))
            self.error.show()
            self.password.selectAll()
            self.password.setFocus()
            return
        self.error.hide()
        self.authenticated.emit(username)

