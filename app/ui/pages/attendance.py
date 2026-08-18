from PyQt6.QtCore import Qt, QThreadPool
from PyQt6.QtWidgets import (
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QMessageBox,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from app.ui.face_capture import FaceCaptureDialog
from app.ui.widgets import TouchCard
from app.ui.workers import TaskWorker


class AttendancePage(QWidget):
    def __init__(self, service, pool: QThreadPool, models_dir, camera_indices):
        super().__init__()
        self.service = service
        self.pool = pool
        self.models_dir = models_dir
        self.camera_indices = camera_indices
        self.busy = False
        self._build()

    def _build(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(32, 28, 32, 28)
        layout.setSpacing(18)
        header = QHBoxLayout()
        title_box = QVBoxLayout()
        title = QLabel("ورود اعضا")
        title.setObjectName("pageTitle")
        subtitle = QLabel("تشخیص خودکار چهره و تخصیص کمد؛ خروج پس از ۶۰ دقیقه خودکار ثبت می‌شود.")
        subtitle.setObjectName("pageSubtitle")
        title_box.addWidget(title)
        title_box.addWidget(subtitle)
        refresh = QPushButton("بازخوانی چهره‌ها")
        refresh.setObjectName("secondaryButton")
        refresh.clicked.connect(self.refresh_faces)
        header.addLayout(title_box)
        header.addStretch()
        header.addWidget(refresh)
        layout.addLayout(header)

        self.summary = QLabel("در حال دریافت وضعیت کمدها…")
        self.summary.setObjectName("attendanceSummary")
        layout.addWidget(self.summary)

        actions = QGridLayout()
        check_in = self._action_card(
            "ورود عضو",
            "کارت را لمس کنید و روبه‌روی دوربین بایستید؛ نیازی به زدن دکمه ثبت چهره نیست.",
            True,
            self.capture,
        )
        actions.addWidget(check_in, 0, 0)
        layout.addLayout(actions)

        self.result = QLabel("آماده ثبت تردد")
        self.result.setObjectName("attendanceResult")
        self.result.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.result.setWordWrap(True)
        layout.addWidget(self.result)
        layout.addStretch()

    def _action_card(self, title, description, primary, callback):
        card = TouchCard("primaryAction" if primary else "actionCard")
        card.setFixedHeight(300)
        card.clicked.connect(callback)
        layout = QVBoxLayout(card)
        layout.setContentsMargins(24, 22, 24, 22)
        heading = QLabel(title)
        heading.setObjectName("actionTitle")
        detail = QLabel(description)
        detail.setObjectName("actionDescription")
        detail.setWordWrap(True)
        hint = QLabel("برای ورود این کارت را لمس کنید")
        hint.setObjectName("actionLink")
        layout.addWidget(heading)
        layout.addWidget(detail)
        layout.addStretch()
        layout.addWidget(hint)
        card.make_children_transparent()
        return card

    def showEvent(self, event):
        super().showEvent(event)
        self.refresh_summary()

    def refresh_faces(self):
        self._run(
            self.service.refresh_faces,
            lambda count: self._set_result(f"اطلاعات چهره {count} عضو بازخوانی شد."),
        )

    def refresh_summary(self):
        worker = TaskWorker(self.service.summary)
        worker.signals.succeeded.connect(
            lambda value: self.summary.setText(
                f"افراد حاضر: {value['inside']:,}     |     کمد خالی: {value['free_lockers']:,}"
            )
        )
        worker.signals.failed.connect(lambda message: self.summary.setText(message))
        self.pool.start(worker)

    def capture(self):
        if self.busy:
            return
        dialog = FaceCaptureDialog(
            self.models_dir,
            self.camera_indices,
            self,
            auto_capture=True,
        )
        dialog.captured.connect(
            lambda embedding, image: self._process(embedding)
        )
        dialog.exec()

    def _process(self, embedding):
        self._run(self.service.check_in, self._show_result, embedding)

    def _run(self, operation, success, *args):
        if self.busy:
            return
        self.busy = True
        self.result.setText("در حال پردازش…")
        worker = TaskWorker(operation, *args)
        worker.signals.succeeded.connect(success)
        worker.signals.failed.connect(self._failed)
        worker.signals.finished.connect(self._finished)
        self.pool.start(worker)

    def _show_result(self, result):
        locker = f" — کمد {result.locker_id}" if result.locker_id else ""
        remaining = result.member.remaining_sessions
        session_message = ""
        if remaining is not None:
            session_message = f"\nجلسات باقی‌مانده: {remaining}"
            if remaining < 0:
                session_message += " — لطفاً عضویت را تمدید کنید."
        self._set_result(
            f"ورود {result.member.full_name} با موفقیت ثبت شد{locker}.{session_message}"
        )
        self.refresh_summary()

    def _set_result(self, message):
        self.result.setText(message)

    def _failed(self, message):
        self.result.setText(message)
        QMessageBox.warning(self, "عملیات انجام نشد", message)

    def _finished(self):
        self.busy = False
