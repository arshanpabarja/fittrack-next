from PyQt6.QtCore import Qt, QThreadPool, pyqtSignal
from PyQt6.QtWidgets import (
    QAbstractItemView,
    QDialog,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPushButton,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from app.ui.workers import TaskWorker


class CoachAccessDialog(QDialog):
    save_requested = pyqtSignal(object)

    def __init__(self, plans, coach=None, parent=None):
        super().__init__(parent)
        self.plans = list(plans)
        self.coach = coach
        self.setWindowTitle("ویرایش دسترسی مربی" if coach else "ساخت حساب مربی")
        self.setModal(True)
        self.resize(620, 650)
        self.setLayoutDirection(Qt.LayoutDirection.RightToLeft)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(28, 24, 28, 24)
        layout.setSpacing(14)

        title = QLabel("ویرایش رمز و پلن‌های مربی" if coach else "ساخت حساب ورود مربی")
        title.setObjectName("dialogTitle")
        description = QLabel(
            "در Life Box فقط شماره ورود، رمز و پلن‌های مجاز تعیین می‌شوند. "
            "نام، تخصص، معرفی و برنامه‌های تمرینی را مربی داخل سایت تکمیل می‌کند."
        )
        description.setObjectName("membershipStatus")
        description.setWordWrap(True)
        layout.addWidget(title)
        layout.addWidget(description)

        mobile_label = QLabel("شماره موبایل (نام کاربری)")
        mobile_label.setObjectName("fieldLabel")
        self.mobile = QLineEdit(coach.mobile if coach else "")
        self.mobile.setInputMask("00000000000")
        self.mobile.setEnabled(coach is None)
        password_label = QLabel("رمز عبور" + (" (برای حفظ رمز فعلی خالی بگذارید)" if coach else ""))
        password_label.setObjectName("fieldLabel")
        self.password = QLineEdit()
        self.password.setEchoMode(QLineEdit.EchoMode.Password)
        confirm_label = QLabel("تکرار رمز عبور")
        confirm_label.setObjectName("fieldLabel")
        self.confirm = QLineEdit()
        self.confirm.setEchoMode(QLineEdit.EchoMode.Password)
        layout.addWidget(mobile_label)
        layout.addWidget(self.mobile)
        layout.addWidget(password_label)
        layout.addWidget(self.password)
        layout.addWidget(confirm_label)
        layout.addWidget(self.confirm)

        plans_label = QLabel("پلن‌هایی که مربی اجازه مدیریت آن‌ها را دارد")
        plans_label.setObjectName("fieldLabel")
        layout.addWidget(plans_label)
        self.plan_table = QTableWidget(len(self.plans), 2)
        self.plan_table.setHorizontalHeaderLabels(["انتخاب", "پلن باشگاه"])
        self.plan_table.setSelectionMode(QAbstractItemView.SelectionMode.NoSelection)
        self.plan_table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.plan_table.verticalHeader().hide()
        self.plan_table.verticalHeader().setDefaultSectionSize(52)
        self.plan_table.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeMode.ResizeToContents)
        self.plan_table.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeMode.Stretch)
        selected = set(coach.plan_ids if coach else ())
        for row, plan in enumerate(self.plans):
            check = QTableWidgetItem()
            check.setFlags(Qt.ItemFlag.ItemIsEnabled | Qt.ItemFlag.ItemIsUserCheckable)
            check.setCheckState(Qt.CheckState.Checked if plan.id in selected else Qt.CheckState.Unchecked)
            name = QTableWidgetItem(plan.name)
            name.setTextAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
            self.plan_table.setItem(row, 0, check)
            self.plan_table.setItem(row, 1, name)
        layout.addWidget(self.plan_table, 1)

        self.error = QLabel()
        self.error.setObjectName("formError")
        self.error.setWordWrap(True)
        self.error.hide()
        layout.addWidget(self.error)
        actions = QHBoxLayout()
        self.save_button = QPushButton("ذخیره دسترسی مربی")
        self.save_button.clicked.connect(self._submit)
        cancel = QPushButton("انصراف")
        cancel.setObjectName("secondaryButton")
        cancel.clicked.connect(self.reject)
        actions.addWidget(self.save_button)
        actions.addWidget(cancel)
        layout.addLayout(actions)

    def _submit(self):
        if self.password.text() != self.confirm.text():
            self.operation_failed("رمز عبور و تکرار آن یکسان نیست.")
            return
        selected = [
            plan.id
            for row, plan in enumerate(self.plans)
            if self.plan_table.item(row, 0).checkState() == Qt.CheckState.Checked
        ]
        self.error.hide()
        self.save_button.setEnabled(False)
        self.save_button.setText("در حال ذخیره در سایت…")
        self.save_requested.emit({
            "mobile": self.mobile.text(),
            "password": self.password.text(),
            "plan_ids": selected,
        })

    def operation_failed(self, message):
        self.error.setText(message)
        self.error.show()
        self.save_button.setEnabled(True)
        self.save_button.setText("ذخیره دسترسی مربی")


class CoachesPage(QWidget):
    def __init__(self, service, pool: QThreadPool):
        super().__init__()
        self.service = service
        self.pool = pool
        self.plans = []
        self.coaches = []
        self.busy = False
        self._build()

    def _build(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(32, 28, 32, 28)
        layout.setSpacing(16)
        header = QHBoxLayout()
        title_box = QVBoxLayout()
        title = QLabel("دسترسی مربیان سایت")
        title.setObjectName("pageTitle")
        subtitle = QLabel("ساخت حساب ورود، تعیین رمز و انتخاب پلن‌های مجاز؛ پنل اصلی مربی داخل سایت است.")
        subtitle.setObjectName("pageSubtitle")
        title_box.addWidget(title)
        title_box.addWidget(subtitle)
        add = QPushButton("ساخت حساب مربی")
        add.clicked.connect(self._add_coach)
        header.addLayout(title_box)
        header.addStretch()
        header.addWidget(add)
        layout.addLayout(header)

        self.notice = QLabel("در حال اتصال به سایت…")
        self.notice.setObjectName("pageNotice")
        layout.addWidget(self.notice)
        self.table = QTableWidget(0, 5)
        self.table.setHorizontalHeaderLabels(["شماره ورود", "نام در سایت", "تخصص", "پلن‌های مجاز", "شناسه"])
        self.table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.table.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self.table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.table.verticalHeader().hide()
        self.table.verticalHeader().setDefaultSectionSize(62)
        self.table.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeMode.ResizeToContents)
        self.table.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeMode.ResizeToContents)
        self.table.horizontalHeader().setSectionResizeMode(2, QHeaderView.ResizeMode.ResizeToContents)
        self.table.horizontalHeader().setSectionResizeMode(3, QHeaderView.ResizeMode.Stretch)
        self.table.setColumnHidden(4, True)
        self.table.doubleClicked.connect(self._edit_coach)
        layout.addWidget(self.table, 1)

        footer = QHBoxLayout()
        edit = QPushButton("تغییر رمز یا پلن‌ها")
        edit.clicked.connect(self._edit_coach)
        note = QLabel("مربی با همین شماره در سایت وارد می‌شود و اطلاعات و برنامه‌ها را آنجا مدیریت می‌کند.")
        note.setObjectName("pageSubtitle")
        footer.addWidget(edit)
        footer.addStretch()
        footer.addWidget(note)
        layout.addLayout(footer)

    def showEvent(self, event):
        super().showEvent(event)
        if not self.busy:
            self.refresh()

    def refresh(self):
        if self.busy:
            return
        self.busy = True
        self.notice.setText("در حال دریافت حساب‌های مربی از سایت…")
        worker = TaskWorker(self.service.load)
        worker.signals.succeeded.connect(self._render)
        worker.signals.failed.connect(lambda message: self.notice.setText(message))
        worker.signals.finished.connect(self._finished)
        self.pool.start(worker)

    def _finished(self):
        self.busy = False

    def _render(self, result):
        plans, coaches = result
        self.plans = list(plans)
        self.coaches = list(coaches)
        self.table.setRowCount(len(self.coaches))
        for row, coach in enumerate(self.coaches):
            values = (
                coach.mobile,
                coach.full_name or "هنوز تکمیل نشده",
                coach.specialty or "—",
                "، ".join(coach.plans) or "بدون پلن",
                str(coach.id),
            )
            for column, value in enumerate(values):
                cell = QTableWidgetItem(value)
                cell.setTextAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
                self.table.setItem(row, column, cell)
        self.notice.setText("هنوز حساب مربی ساخته نشده است." if not self.coaches else "")

    def _selected(self):
        row = self.table.currentRow()
        return self.coaches[row] if 0 <= row < len(self.coaches) else None

    def _add_coach(self):
        if not self.plans:
            QMessageBox.warning(self, "پلن موجود نیست", "ابتدا اتصال سایت و پلن‌های فعال را بررسی کنید.")
            return
        self._open_dialog(None)

    def _edit_coach(self):
        coach = self._selected()
        if coach:
            self._open_dialog(coach)

    def _open_dialog(self, coach):
        dialog = CoachAccessDialog(self.plans, coach, self)
        dialog.save_requested.connect(
            lambda values: self._save(dialog, coach, values)
        )
        dialog.exec()

    def _save(self, dialog, coach, values):
        worker = TaskWorker(
            self.service.save_coach,
            values,
            coach.id if coach else None,
        )
        worker.signals.succeeded.connect(lambda result: self._saved(dialog, result))
        worker.signals.failed.connect(dialog.operation_failed)
        self.pool.start(worker)

    def _saved(self, dialog, coach):
        dialog.accept()
        QMessageBox.information(
            self,
            "دسترسی ذخیره شد",
            f"حساب {coach.mobile} در سایت آماده است. مربی می‌تواند وارد پنل وب شود.",
        )
        self.refresh()
