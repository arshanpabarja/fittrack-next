from PyQt6.QtCore import QThreadPool
from PyQt6.QtWidgets import (
    QFormLayout,
    QComboBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from app.ui.workers import TaskWorker


class SettingsPage(QWidget):
    def __init__(self, service, pool: QThreadPool):
        super().__init__()
        self.service = service
        self.pool = pool
        self.loaded = False
        self._build()

    def _build(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(32, 28, 32, 28)
        layout.setSpacing(18)
        title = QLabel("تنظیمات سیستم")
        title.setObjectName("pageTitle")
        subtitle = QLabel("تنظیمات متمرکز نسخه جدید؛ تغییرات حساس پس از اجرای دوباره اعمال می‌شوند.")
        subtitle.setObjectName("pageSubtitle")
        layout.addWidget(title)
        layout.addWidget(subtitle)
        form = QFormLayout()
        form.setSpacing(14)
        self.api_url = QLineEdit()
        self.camera_indices = QLineEdit()
        self.face_threshold = QLineEdit()
        self.pos_mode = QComboBox()
        self.pos_mode.addItem("کارتخوان واقعی", "real")
        self.pos_mode.addItem("آزمایشی — بدون برداشت وجه", "fake")
        self.pos_host = QLineEdit()
        self.pos_port = QLineEdit()
        self.pos_timeout = QLineEdit()
        form.addRow("آدرس Django API", self.api_url)
        form.addRow("شماره دوربین‌ها", self.camera_indices)
        form.addRow("آستانه تشخیص چهره", self.face_threshold)
        form.addRow("حالت دستگاه POS", self.pos_mode)
        form.addRow("IP کارتخوان", self.pos_host)
        form.addRow("پورت کارتخوان", self.pos_port)
        form.addRow("زمان انتظار (ثانیه)", self.pos_timeout)
        layout.addLayout(form)
        self.notice = QLabel()
        self.notice.setObjectName("pageNotice")
        self.notice.setWordWrap(True)
        layout.addWidget(self.notice)
        buttons = QHBoxLayout()
        save = QPushButton("ذخیره تنظیمات")
        save.clicked.connect(self.save)
        reload_button = QPushButton("بازخوانی")
        reload_button.setObjectName("secondaryButton")
        reload_button.clicked.connect(self.load)
        buttons.addWidget(save)
        buttons.addWidget(reload_button)
        buttons.addStretch()
        layout.addLayout(buttons)
        layout.addStretch()

    def showEvent(self, event):
        super().showEvent(event)
        if not self.loaded:
            self.load()

    def load(self):
        worker = TaskWorker(self.service.load)
        worker.signals.succeeded.connect(self._render)
        worker.signals.failed.connect(lambda message: self.notice.setText(message))
        self.pool.start(worker)

    def _render(self, values):
        self.loaded = True
        self.api_url.setText(values["api_url"])
        self.camera_indices.setText(values["camera_indices"])
        self.face_threshold.setText(values["face_threshold"])
        self.pos_mode.setCurrentIndex(self.pos_mode.findData(values["pos_mode"]))
        self.pos_host.setText(values["pos_host"])
        self.pos_port.setText(values["pos_port"])
        self.pos_timeout.setText(values["pos_timeout"])
        self.notice.setText("")

    def save(self):
        values = {
            "api_url": self.api_url.text(),
            "camera_indices": self.camera_indices.text(),
            "face_threshold": self.face_threshold.text(),
            "pos_mode": self.pos_mode.currentData(),
            "pos_host": self.pos_host.text(),
            "pos_port": self.pos_port.text(),
            "pos_timeout": self.pos_timeout.text(),
        }
        worker = TaskWorker(self.service.save, values)
        worker.signals.succeeded.connect(self._saved)
        worker.signals.failed.connect(lambda message: self.notice.setText(message))
        self.pool.start(worker)

    def _saved(self, values):
        self._render(values)
        self.notice.setText("تنظیمات ذخیره شد؛ برای اعمال کامل برنامه را دوباره اجرا کنید.")
