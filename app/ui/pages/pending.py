from PyQt6.QtCore import Qt, QThreadPool, QTimer, pyqtSignal
from PyQt6.QtWidgets import (
    QAbstractItemView,
    QComboBox,
    QDialog,
    QFormLayout,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPushButton,
    QSpinBox,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from app.ui.face_capture import FaceCaptureDialog
from app.ui.workers import TaskWorker


class EnrollmentDialog(QDialog):
    completed = pyqtSignal()

    def __init__(self, application, service, pool, models_dir, camera_indices, parent=None):
        super().__init__(parent)
        self.application = application
        self.service = service
        self.pool = pool
        self.models_dir = models_dir
        self.camera_indices = camera_indices
        self.state = service.start(application)
        self.busy = False
        self.auto_capture_started = False
        self.setWindowTitle("تکمیل عضویت")
        self.setModal(True)
        self.resize(650, 660)
        self._build()
        self._render_state()

    def _build(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(30, 26, 30, 26)
        layout.setSpacing(16)
        title = QLabel(f"تکمیل عضویت {self.application.full_name}")
        title.setObjectName("dialogTitle")
        summary = QLabel(
            f"{self.application.mobile}  •  {self.application.plan}\n"
            f"مبلغ پلن: {self.application.price:,} تومان"
        )
        summary.setObjectName("enrollmentSummary")
        layout.addWidget(title)
        layout.addWidget(summary)

        form = QFormLayout()
        form.setSpacing(12)
        self.father_name = QLineEdit()
        self.father_name.setPlaceholderText("اختیاری")
        self.certificate_no = QLineEdit()
        self.certificate_no.setPlaceholderText("اختیاری")
        self.age = QSpinBox()
        self.age.setRange(0, 120)
        self.age.setSpecialValueText("نامشخص")
        self.gender = QComboBox()
        self.gender.addItems(["مرد", "زن"])
        if self.application.gender == "female":
            self.gender.setCurrentText("زن")
        form.addRow("نام پدر", self.father_name)
        form.addRow("شماره شناسنامه", self.certificate_no)
        form.addRow("سن", self.age)
        form.addRow("جنسیت", self.gender)
        layout.addLayout(form)

        self.face_status = QLabel()
        self.face_status.setObjectName("workflowStatus")
        self.payment_status = QLabel()
        self.payment_status.setObjectName("workflowStatus")
        self.payment_button = QPushButton("پرداخت آزمایشی")
        self.payment_button.clicked.connect(self.take_payment)
        actions = QHBoxLayout()
        actions.addWidget(self.payment_button)
        layout.addWidget(self.face_status)
        layout.addWidget(self.payment_status)
        layout.addLayout(actions)

        self.error = QLabel()
        self.error.setObjectName("formError")
        self.error.setWordWrap(True)
        self.error.hide()
        layout.addWidget(self.error)
        layout.addStretch()
        footer = QHBoxLayout()
        self.complete_button = QPushButton("ساخت عضو و فعال‌سازی حساب")
        self.complete_button.clicked.connect(self.complete)
        close = QPushButton("بستن")
        close.setObjectName("secondaryButton")
        close.clicked.connect(self.reject)
        footer.addWidget(self.complete_button)
        footer.addWidget(close)
        layout.addLayout(footer)

    def _render_state(self):
        self.face_status.setText(
            "چهره: ثبت شده" if self.state.face_captured else "چهره: هنوز ثبت نشده"
        )
        if self.state.paid_amount:
            self.payment_status.setText(
                f"پرداخت: {self.state.paid_amount:,} تومان — {self.state.payment_reference}"
            )
        else:
            self.payment_status.setText("پرداخت: هنوز انجام نشده")
        ready = self.state.face_captured and self.state.paid_amount >= self.application.price
        self.complete_button.setEnabled(ready and not self.busy)
        self.payment_button.setEnabled(not self.busy and self.state.paid_amount < self.application.price)
        if self.state.last_error:
            self.error.setText(self.state.last_error)
            self.error.show()

    def _set_busy(self, busy):
        self.busy = busy
        self._render_state()

    def capture_face(self):
        dialog = FaceCaptureDialog(
            self.models_dir,
            self.camera_indices,
            self,
            auto_capture=True,
        )
        dialog.captured.connect(self._save_face)
        dialog.exec()

    def showEvent(self, event):
        super().showEvent(event)
        if not self.state.face_captured and not self.auto_capture_started:
            self.auto_capture_started = True
            QTimer.singleShot(250, self.capture_face)

    def _save_face(self, embedding, image):
        self._set_busy(True)
        worker = TaskWorker(
            self.service.save_face,
            self.application.id,
            embedding,
            image,
        )
        worker.signals.succeeded.connect(self._state_changed)
        worker.signals.failed.connect(self._failed)
        worker.signals.finished.connect(lambda: self._set_busy(False))
        self.pool.start(worker)

    def take_payment(self):
        self.error.hide()
        self._set_busy(True)
        worker = TaskWorker(self.service.take_payment, self.application)
        worker.signals.succeeded.connect(self._payment_complete)
        worker.signals.failed.connect(self._failed)
        worker.signals.finished.connect(lambda: self._set_busy(False))
        self.pool.start(worker)

    def _payment_complete(self, receipt):
        self.state = self.service.workflows.get(self.application.id)
        self._render_state()

    def _state_changed(self, state):
        self.state = state
        self.error.hide()
        self._render_state()

    def _failed(self, message):
        self.error.setText(message)
        self.error.show()

    def complete(self):
        details = {
            "father_name": self.father_name.text().strip(),
            "certificate_no": self.certificate_no.text().strip(),
            "age": self.age.value() or None,
            "gender": self.gender.currentText(),
        }
        self.error.hide()
        self._set_busy(True)
        self.complete_button.setText("در حال فعال‌سازی…")
        worker = TaskWorker(self.service.complete, self.application, details)
        worker.signals.succeeded.connect(self._completed)
        worker.signals.failed.connect(self._failed)
        worker.signals.finished.connect(self._complete_finished)
        self.pool.start(worker)

    def _complete_finished(self):
        self.complete_button.setText("ساخت عضو و فعال‌سازی حساب")
        self._set_busy(False)

    def _completed(self, member_id):
        QMessageBox.information(
            self,
            "عضویت فعال شد",
            f"عضو با شناسه {member_id} ساخته شد و حساب سایت فعال شد.",
        )
        self.completed.emit()
        self.accept()


class PendingApplicationsPage(QWidget):
    membership_activated = pyqtSignal()

    def __init__(self, pending_service, enrollment_service, pool, models_dir, camera_indices):
        super().__init__()
        self.pending_service = pending_service
        self.enrollment_service = enrollment_service
        self.pool = pool
        self.models_dir = models_dir
        self.camera_indices = camera_indices
        self.items = []
        self.busy = False
        self._build()

    def _build(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(32, 28, 32, 28)
        layout.setSpacing(16)
        header = QHBoxLayout()
        title_box = QVBoxLayout()
        title = QLabel("پذیرش کاربر از سایت")
        title.setObjectName("pageTitle")
        subtitle = QLabel("تشخیص خودکار چهره، پرداخت و فعال‌سازی نهایی حساب‌های در انتظار")
        subtitle.setObjectName("pageSubtitle")
        title_box.addWidget(title)
        title_box.addWidget(subtitle)
        self.mobile = QLineEdit()
        self.mobile.setPlaceholderText("جستجو با شماره موبایل")
        self.mobile.setFixedWidth(260)
        self.mobile.returnPressed.connect(self.refresh)
        self.refresh_button = QPushButton("دریافت از سایت")
        self.refresh_button.clicked.connect(self.refresh)
        header.addLayout(title_box)
        header.addStretch()
        header.addWidget(self.mobile)
        header.addWidget(self.refresh_button)
        layout.addLayout(header)
        self.notice = QLabel()
        self.notice.setObjectName("pageNotice")
        layout.addWidget(self.notice)
        self.table = QTableWidget(0, 7)
        self.table.setHorizontalHeaderLabels(
            ["نام و نام خانوادگی", "موبایل", "کد ملی", "پلن", "مبلغ", "زمان درخواست", "شناسه"]
        )
        self.table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.table.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self.table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.table.setAlternatingRowColors(True)
        self.table.verticalHeader().hide()
        self.table.verticalHeader().setDefaultSectionSize(54)
        self.table.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
        for column in range(1, 6):
            self.table.horizontalHeader().setSectionResizeMode(column, QHeaderView.ResizeMode.ResizeToContents)
        self.table.setColumnHidden(6, True)
        self.table.doubleClicked.connect(self.open_selected)
        layout.addWidget(self.table, 1)
        footer = QHBoxLayout()
        self.open_button = QPushButton("شروع پذیرش عضو")
        self.open_button.clicked.connect(self.open_selected)
        self.open_button.setEnabled(False)
        self.table.itemSelectionChanged.connect(self._update_controls)
        footer.addWidget(self.open_button)
        footer.addStretch()
        layout.addLayout(footer)

    def showEvent(self, event):
        super().showEvent(event)
        if not self.items and not self.busy:
            self.refresh()

    def refresh(self):
        if self.busy:
            return
        self.busy = True
        self.notice.setText("در حال اتصال به سایت…")
        self.refresh_button.setEnabled(False)
        self._update_controls()
        worker = TaskWorker(self.pending_service.list_pending, self.mobile.text())
        worker.signals.succeeded.connect(self._render)
        worker.signals.failed.connect(self._failed)
        worker.signals.finished.connect(self._finish)
        self.pool.start(worker)

    def _render(self, items):
        self.items = list(items)
        self.table.setRowCount(len(items))
        for row, item in enumerate(items):
            values = (
                item.full_name,
                item.mobile,
                item.national_id,
                item.plan,
                f"{item.price:,}",
                item.requested_at,
                str(item.id),
            )
            for column, value in enumerate(values):
                cell = QTableWidgetItem(value)
                cell.setTextAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
                self.table.setItem(row, column, cell)
        self.notice.setText(
            "درخواستی در انتظار نیست." if not items else f"{len(items)} درخواست دریافت شد."
        )

    def _failed(self, message):
        self.notice.setText(message)

    def _finish(self):
        self.busy = False
        self.refresh_button.setEnabled(True)
        self._update_controls()

    def _update_controls(self):
        self.open_button.setEnabled(
            not self.busy and self.table.currentRow() >= 0
        )

    def open_selected(self):
        row = self.table.currentRow()
        if row < 0 or row >= len(self.items) or self.busy:
            return
        dialog = EnrollmentDialog(
            self.items[row],
            self.enrollment_service,
            self.pool,
            self.models_dir,
            self.camera_indices,
            self,
        )
        dialog.completed.connect(self._membership_completed)
        dialog.exec()

    def _membership_completed(self):
        self.membership_activated.emit()
        self.refresh()
