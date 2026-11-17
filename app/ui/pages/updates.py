from PyQt6.QtCore import QThreadPool, QTimer
from PyQt6.QtWidgets import (
    QApplication,
    QFrame,
    QHBoxLayout,
    QLabel,
    QMessageBox,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from app.core.version import APP_VERSION
from app.ui.workers import TaskWorker


class DesktopUpdatesPage(QWidget):
    def __init__(self, telemetry, update_service, audit, pool: QThreadPool):
        super().__init__()
        self.telemetry = telemetry
        self.update_service = update_service
        self.audit = audit
        self.pool = pool
        self.release = None
        self.busy = False
        self._build()

    def _build(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(32, 28, 32, 32)
        layout.setSpacing(18)
        title = QLabel("تغییرات اخیر و به‌روزرسانی")
        title.setObjectName("pageTitle")
        subtitle = QLabel(
            "نسخه‌های منتشرشده از سرور بررسی می‌شوند، اما دانلود و نصب فقط با تأیید دستی شما آغاز خواهد شد."
        )
        subtitle.setObjectName("pageSubtitle")
        subtitle.setWordWrap(True)
        layout.addWidget(title)
        layout.addWidget(subtitle)

        current = QFrame()
        current.setObjectName("card")
        current_layout = QHBoxLayout(current)
        current_layout.addWidget(QLabel("نسخه نصب‌شده"))
        current_layout.addStretch()
        version = QLabel(APP_VERSION)
        version.setObjectName("sectionTitle")
        current_layout.addWidget(version)
        layout.addWidget(current)

        self.release_card = QFrame()
        self.release_card.setObjectName("card")
        release_layout = QVBoxLayout(self.release_card)
        self.release_title = QLabel("در حال بررسی نسخه جدید…")
        self.release_title.setObjectName("sectionTitle")
        self.release_notes = QLabel()
        self.release_notes.setWordWrap(True)
        self.release_notes.setTextInteractionFlags(
            self.release_notes.textInteractionFlags()
        )
        release_layout.addWidget(self.release_title)
        release_layout.addWidget(self.release_notes)
        self.install = QPushButton("دانلود و نصب نسخه جدید")
        self.install.setEnabled(False)
        self.install.clicked.connect(self._confirm_install)
        release_layout.addWidget(self.install)
        layout.addWidget(self.release_card)

        actions = QHBoxLayout()
        self.notice = QLabel()
        self.notice.setObjectName("pageNotice")
        check = QPushButton("بررسی دوباره")
        check.setObjectName("secondaryButton")
        check.clicked.connect(self.check)
        actions.addWidget(self.notice, 1)
        actions.addWidget(check)
        layout.addLayout(actions)
        layout.addStretch()

    def showEvent(self, event):
        super().showEvent(event)
        QTimer.singleShot(0, self.check)

    def check(self):
        if self.busy or not self.telemetry:
            if not self.telemetry:
                self.release_title.setText("بررسی آنلاین نسخه فعال نیست")
                self.release_notes.setText("تنظیمات همگام‌سازی اینترنتی برنامه را بررسی کنید.")
            return
        self.busy = True
        self.notice.setText("در حال بررسی نسخه جدید…")
        worker = TaskWorker(self.telemetry.run)
        worker.signals.succeeded.connect(lambda _: self.render_release())
        worker.signals.failed.connect(self._check_failed)
        worker.signals.finished.connect(lambda: setattr(self, "busy", False))
        self.pool.start(worker)

    def render_release(self):
        self.release = self.telemetry.latest_release if self.telemetry else None
        if not self.release:
            self.release_title.setText("برنامه به‌روز است")
            self.release_notes.setText("نسخه جدیدی برای این دستگاه منتشر نشده است.")
            self.install.setEnabled(False)
        else:
            self.release_title.setText(f"نسخه {self.release['version']} آماده است")
            self.release_notes.setText(self.release.get("notes") or "توضیحی برای این نسخه ثبت نشده است.")
            self.install.setEnabled(bool(self.update_service))
        self.notice.setText("")

    def _check_failed(self, message):
        self.notice.setText(message)
    def _confirm_install(self):
        if not self.release or self.busy:
            return
        answer = QMessageBox.question(
            self,
            "نصب نسخه جدید",
            f"نسخه {self.release['version']} دانلود و نصب شود؟\n"
            "برنامه پس از دانلود بسته می‌شود و در صورت خطا به نسخه فعلی برمی‌گردد.",
        )
        if answer != QMessageBox.StandardButton.Yes:
            return
        self.busy = True
        self.install.setEnabled(False)
        self.install.setText("در حال دانلود و بررسی…")
        worker = TaskWorker(self.update_service.prepare, self.release)
        worker.signals.succeeded.connect(self._prepared)
        worker.signals.failed.connect(self._install_failed)
        worker.signals.finished.connect(lambda: setattr(self, "busy", False))
        self.pool.start(worker)

    def _prepared(self, prepared):
        QMessageBox.information(
            self,
            "نصب نسخه جدید",
            "دانلود و بررسی با موفقیت انجام شد. پس از تأیید این پیام، برنامه برای نصب بسته می‌شود.",
        )
        try:
            self.update_service.launch(prepared)
            self.audit.record(
                "desktop_update",
                entity_type="release",
                entity_id=prepared["version"],
                summary=f"شروع نصب دستی نسخه {prepared['version']}",
            )
        except Exception as exc:
            self._install_failed(str(exc))
            return
        QTimer.singleShot(300, QApplication.instance().quit)

    def _install_failed(self, message):
        self.install.setEnabled(bool(self.release))
        self.install.setText("دانلود و نصب نسخه جدید")
        self.notice.setText(message)
