from PyQt6.QtCore import Qt, QThreadPool, QTimer, pyqtSignal
from PyQt6.QtWidgets import (
    QAbstractItemView,
    QComboBox,
    QFrame,
    QHeaderView,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPushButton,
    QScrollArea,
    QSpinBox,
    QStackedWidget,
    QTableWidget,
    QTableWidgetItem,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)

from app.ui.face_capture import FaceCaptureDialog
from app.ui.workers import TaskWorker


class WalkInSignupPage(QWidget):
    member_created = pyqtSignal()

    def __init__(self, service, pool: QThreadPool, models_dir, camera_indices):
        super().__init__()
        self.service = service
        self.pool = pool
        self.models_dir = models_dir
        self.camera_indices = camera_indices
        self.plans = []
        self.selected_plan = None
        self.profile = None
        self.embedding = None
        self.face_image = None
        self.busy = False
        self._build()

    def _build(self):
        root = QVBoxLayout(self)
        root.setContentsMargins(32, 26, 32, 28)
        root.setSpacing(14)
        title = QLabel("ثبت‌نام حضوری در باشگاه")
        title.setObjectName("pageTitle")
        subtitle = QLabel("انتخاب پلن، ثبت اطلاعات و شناسایی خودکار چهره در سه مرحله")
        subtitle.setObjectName("pageSubtitle")
        self.progress = QLabel("مرحله ۱ از ۳  •  انتخاب پلن")
        self.progress.setObjectName("workflowStatus")
        root.addWidget(title)
        root.addWidget(subtitle)
        root.addWidget(self.progress)

        self.stack = QStackedWidget()
        self.stack.addWidget(self._plans_step())
        self.stack.addWidget(self._profile_step())
        self.stack.addWidget(self._review_step())
        root.addWidget(self.stack, 1)

    def _plans_step(self):
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.setContentsMargins(0, 6, 0, 0)
        self.plan_table = QTableWidget(0, 2)
        self.plan_table.setHorizontalHeaderLabels(["پلن عضویت", "مبلغ (تومان)"])
        self.plan_table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.plan_table.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self.plan_table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.plan_table.verticalHeader().hide()
        self.plan_table.verticalHeader().setDefaultSectionSize(62)
        self.plan_table.horizontalHeader().setStretchLastSection(False)
        self.plan_table.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
        self.plan_table.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeMode.ResizeToContents)
        self.plan_table.itemSelectionChanged.connect(
            lambda: self.plan_next.setEnabled(self.plan_table.currentRow() >= 0)
        )
        layout.addWidget(self.plan_table, 1)
        self.plan_next = QPushButton("ادامه و ثبت اطلاعات")
        self.plan_next.setEnabled(False)
        self.plan_next.clicked.connect(self._select_plan)
        layout.addWidget(self.plan_next)
        return page

    @staticmethod
    def _labeled(layout, label, widget, optional=False):
        title = QLabel(f"{label}{' (اختیاری)' if optional else ''}")
        title.setObjectName("fieldLabel")
        layout.addWidget(title)
        layout.addWidget(widget)

    def _profile_step(self):
        page = QWidget()
        outer = QVBoxLayout(page)
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.Shape.NoFrame)
        content = QWidget()
        form = QVBoxLayout(content)
        form.setContentsMargins(8, 6, 16, 8)
        form.setSpacing(8)
        self.full_name = QLineEdit()
        self.mobile = QLineEdit()
        self.mobile.setInputMask("00000000000")
        self.national_id = QLineEdit()
        self.national_id.setInputMask("0000000000")
        self.father_name = QLineEdit()
        self.certificate_no = QLineEdit()
        self.age = QSpinBox()
        self.age.setRange(0, 120)
        self.age.setSpecialValueText("نامشخص")
        self.gender = QComboBox()
        self.gender.addItems(["مرد", "زن"])
        self.address = QTextEdit()
        self.address.setMaximumHeight(92)
        self._labeled(form, "نام و نام خانوادگی", self.full_name)
        self._labeled(form, "شماره موبایل", self.mobile)
        self._labeled(form, "کد ملی", self.national_id)
        self._labeled(form, "نام پدر", self.father_name, True)
        self._labeled(form, "شماره شناسنامه", self.certificate_no, True)
        self._labeled(form, "سن", self.age, True)
        self._labeled(form, "جنسیت", self.gender)
        self._labeled(form, "آدرس", self.address)
        form.addStretch()
        scroll.setWidget(content)
        outer.addWidget(scroll, 1)
        actions = QHBoxLayout()
        review = QPushButton("ادامه و ثبت خودکار چهره")
        review.clicked.connect(self._to_review)
        back = QPushButton("بازگشت به پلن‌ها")
        back.setObjectName("secondaryButton")
        back.clicked.connect(lambda: self._show_step(0))
        actions.addWidget(review)
        actions.addWidget(back)
        outer.addLayout(actions)
        return page

    def _review_step(self):
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.setContentsMargins(8, 8, 8, 8)
        layout.setSpacing(16)
        self.review_summary = QLabel()
        self.review_summary.setObjectName("enrollmentSummary")
        self.review_summary.setWordWrap(True)
        self.face_status = QLabel("دوربین پس از ورود به این مرحله خودکار باز می‌شود.")
        self.face_status.setObjectName("workflowStatus")
        self.face_status.setWordWrap(True)
        self.rescan_button = QPushButton("اسکن مجدد چهره")
        self.rescan_button.setObjectName("secondaryButton")
        self.rescan_button.clicked.connect(self._capture_face)
        self.register_button = QPushButton("پرداخت و ساخت عضو")
        self.register_button.setEnabled(False)
        self.register_button.clicked.connect(self._register)
        back = QPushButton("ویرایش اطلاعات")
        back.setObjectName("secondaryButton")
        back.clicked.connect(lambda: self._show_step(1))
        layout.addWidget(self.review_summary)
        layout.addWidget(self.face_status)
        layout.addWidget(self.rescan_button)
        layout.addStretch()
        layout.addWidget(self.register_button)
        layout.addWidget(back)
        return page

    def showEvent(self, event):
        super().showEvent(event)
        if not self.plans:
            self._load_plans()

    def _load_plans(self):
        try:
            self.plans = list(self.service.list_plans())
        except Exception as exc:
            QMessageBox.warning(self, "پلن‌ها خوانده نشد", str(exc))
            return
        self.plan_table.setRowCount(len(self.plans))
        for row, plan in enumerate(self.plans):
            for column, value in enumerate((plan.name, f"{plan.price:,}")):
                item = QTableWidgetItem(value)
                item.setTextAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
                self.plan_table.setItem(row, column, item)

    def _show_step(self, index):
        self.stack.setCurrentIndex(index)
        labels = ("انتخاب پلن", "اطلاعات عضو", "چهره و پرداخت")
        self.progress.setText(f"مرحله {index + 1} از ۳  •  {labels[index]}")

    def _select_plan(self):
        row = self.plan_table.currentRow()
        if row < 0:
            return
        self.selected_plan = self.plans[row]
        self._show_step(1)

    def _profile_values(self):
        return {
            "full_name": self.full_name.text(),
            "mobile": self.mobile.text(),
            "national_id": self.national_id.text(),
            "father_name": self.father_name.text(),
            "certificate_no": self.certificate_no.text(),
            "age": self.age.value() or None,
            "gender": self.gender.currentText(),
            "address": self.address.toPlainText(),
        }

    def _to_review(self):
        try:
            self.profile = self.service.validate_profile(self._profile_values())
        except Exception as exc:
            QMessageBox.warning(self, "اطلاعات ناقص است", str(exc))
            return
        self.embedding = None
        self.face_image = None
        self.register_button.setEnabled(False)
        self.face_status.setText("در حال آماده‌سازی تشخیص خودکار چهره…")
        self.review_summary.setText(
            f"{self.profile['first_name']} {self.profile['last_name']}  •  {self.profile['mobile']}\n"
            f"{self.selected_plan.name}\nمبلغ: {self.selected_plan.price:,} تومان"
        )
        self._show_step(2)
        QTimer.singleShot(250, self._capture_face)

    def _capture_face(self):
        if self.busy or self.stack.currentIndex() != 2:
            return
        self.rescan_button.setEnabled(False)
        self.register_button.setEnabled(False)
        dialog = FaceCaptureDialog(
            self.models_dir,
            self.camera_indices,
            self,
            auto_capture=True,
            capture_delay=4,
        )
        dialog.captured.connect(self._face_captured)
        dialog.exec()
        self.rescan_button.setEnabled(True)
        self.register_button.setEnabled(self.embedding is not None)
        if self.embedding is None:
            self.face_status.setText("چهره ثبت نشد؛ دکمهٔ «اسکن مجدد چهره» را بزنید.")

    def _face_captured(self, embedding, image):
        self.embedding = embedding
        self.face_image = image
        self.face_status.setText("چهره با موفقیت و به‌صورت خودکار ثبت شد.")
        self.register_button.setEnabled(True)

    def _register(self):
        if self.busy:
            return
        self.busy = True
        self.register_button.setEnabled(False)
        self.register_button.setText("در حال پرداخت و ساخت عضو…")
        self.rescan_button.setEnabled(False)
        worker = TaskWorker(
            self.service.register,
            self.profile,
            self.selected_plan,
            self.embedding,
            self.face_image,
        )
        worker.signals.succeeded.connect(self._completed)
        worker.signals.failed.connect(self._failed)
        worker.signals.finished.connect(self._finished)
        self.pool.start(worker)

    def _completed(self, result):
        QMessageBox.information(
            self,
            "عضویت ساخته شد",
            f"عضویت {result.full_name} با شناسه {result.member_id} ساخته شد.\n"
            f"رسید پرداخت: {result.payment_reference}",
        )
        self.member_created.emit()
        self._reset()

    def _failed(self, message):
        QMessageBox.warning(self, "ثبت‌نام انجام نشد", message)

    def _finished(self):
        self.busy = False
        self.rescan_button.setEnabled(True)
        self.register_button.setText("پرداخت و ساخت عضو")
        self.register_button.setEnabled(self.embedding is not None)

    def _reset(self):
        for field in (self.full_name, self.mobile, self.national_id, self.father_name, self.certificate_no):
            field.clear()
        self.address.clear()
        self.age.setValue(0)
        self.embedding = self.face_image = self.profile = self.selected_plan = None
        self.plan_table.clearSelection()
        self.plan_next.setEnabled(False)
        self._show_step(0)
