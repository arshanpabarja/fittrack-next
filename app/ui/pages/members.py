from PyQt6.QtCore import Qt, QThreadPool, QTimer, pyqtSignal
from PyQt6.QtWidgets import (
    QAbstractItemView,
    QCheckBox,
    QComboBox,
    QDialog,
    QFrame,
    QFormLayout,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPushButton,
    QScrollArea,
    QSpinBox,
    QTableWidget,
    QTableWidgetItem,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)

from app.ui.workers import TaskWorker
from app.domain.membership import session_allowance
from app.domain.dates import normalize_membership_datetime


class MemberDialog(QDialog):
    save_requested = pyqtSignal(object)
    delete_requested = pyqtSignal()
    renew_requested = pyqtSignal(object, object)
    password_reset_requested = pyqtSignal(str, str)

    def __init__(self, member, parent=None, plans=()):
        super().__init__(parent)
        self.member = member
        self.plans = tuple(plans)
        self.setWindowTitle("ویرایش عضو")
        self.setModal(True)
        self.resize(680, 780)
        self.setLayoutDirection(Qt.LayoutDirection.RightToLeft)
        outer = QVBoxLayout(self)
        outer.setContentsMargins(28, 24, 28, 24)
        outer.setSpacing(14)
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.Shape.NoFrame)
        content = QWidget()
        layout = QVBoxLayout(content)
        layout.setContentsMargins(0, 0, 10, 0)
        layout.setSpacing(16)
        scroll.setWidget(content)
        title = QLabel(f"ویرایش اطلاعات {member.full_name}")
        title.setObjectName("dialogTitle")
        layout.addWidget(title)

        remaining = member.remaining_sessions
        if remaining is None:
            session_text = "تعداد جلسات این پلن مشخص نیست."
        else:
            session_text = f"جلسات باقی‌مانده: {remaining} از {member.session_allowance} جلسه"
            if remaining < 0:
                session_text += " — عضو در مهلت تمدید است."
            elif remaining == 0:
                session_text += " — جلسات پلن تمام شده است."
        self.session_status = QLabel(session_text)
        self.session_status.setObjectName("membershipStatus")
        self.session_status.setWordWrap(True)
        layout.addWidget(self.session_status)

        form = QFormLayout()
        form.setSpacing(12)
        form.setLabelAlignment(Qt.AlignmentFlag.AlignRight)
        self.first_name = self._line(member.first_name)
        self.last_name = self._line(member.last_name)
        self.father_name = self._line(member.father_name)
        self.mobile = self._line(member.mobile)
        self.national_id = self._line(member.national_id)
        self.certificate_no = self._line(member.certificate_no)
        self.plan = self._line(member.plan)
        self.original_signup_time = normalize_membership_datetime(member.signup_time)
        self.signup_time = QLineEdit(self.original_signup_time)
        self.signup_time.setPlaceholderText("1405/06/30")
        self.signup_time.setToolTip("تاریخ شمسی؛ ساعت اختیاری است، مانند 1405/06/30 09:30")
        self.signup_time.setLayoutDirection(Qt.LayoutDirection.LeftToRight)
        self.remaining_sessions = QSpinBox()
        self.remaining_sessions.setSuffix(" جلسه")
        self.remaining_sessions.setToolTip("عدد منفی یعنی جلسات استفاده‌شده در مهلت تمدید.")
        self.plan.textChanged.connect(self._update_remaining_sessions)
        self._update_remaining_sessions(self.plan.text())
        self.age = QSpinBox()
        self.age.setRange(0, 120)
        self.age.setSpecialValueText("نامشخص")
        self.age.setValue(member.age or 0)
        self.gender = QComboBox()
        self.gender.addItems(["مرد", "زن"])
        self.gender.setCurrentText(member.gender)
        self.debt = QSpinBox()
        self.debt.setRange(0, 2_000_000_000)
        self.debt.setSingleStep(100_000)
        self.debt.setValue(member.debt)
        self.payment = QSpinBox()
        self.payment.setRange(0, 2_000_000_000)
        self.payment.setSingleStep(100_000)
        self.payment.setValue(member.payment)
        self.address = QTextEdit(member.address)
        self.address.setMaximumHeight(90)
        form.addRow("نام", self.first_name)
        form.addRow("نام خانوادگی", self.last_name)
        form.addRow("نام پدر", self.father_name)
        form.addRow("شماره موبایل", self.mobile)
        form.addRow("کد ملی", self.national_id)
        form.addRow("شماره شناسنامه", self.certificate_no)
        form.addRow("سن", self.age)
        form.addRow("جنسیت", self.gender)
        form.addRow("پلن", self.plan)
        form.addRow("تاریخ ثبت‌نام", self.signup_time)
        form.addRow("جلسات باقی‌مانده", self.remaining_sessions)
        form.addRow("بدهی", self.debt)
        form.addRow("پرداخت", self.payment)
        form.addRow("آدرس", self.address)
        layout.addLayout(form)

        password_title = QLabel("رمز ورود سایت")
        password_title.setObjectName("sectionTitle")
        password_hint = QLabel(
            "رمز فعلی به دلیل ذخیره امن و هش‌شده قابل نمایش نیست؛ "
            "اینجا می‌توانید یک رمز جدید تعیین کنید."
        )
        password_hint.setObjectName("pageSubtitle")
        password_hint.setWordWrap(True)
        layout.addWidget(password_title)
        layout.addWidget(password_hint)
        password_form = QFormLayout()
        password_form.setSpacing(10)
        password_form.setLabelAlignment(Qt.AlignmentFlag.AlignRight)
        self.site_password = QLineEdit()
        self.site_password.setEchoMode(QLineEdit.EchoMode.Password)
        self.site_password.setPlaceholderText("حداقل ۸ کاراکتر")
        self.site_password_confirm = QLineEdit()
        self.site_password_confirm.setEchoMode(QLineEdit.EchoMode.Password)
        self.show_site_password = QCheckBox("نمایش رمز جدید")
        self.show_site_password.toggled.connect(self._toggle_site_password)
        password_form.addRow("رمز جدید", self.site_password)
        password_form.addRow("تکرار رمز", self.site_password_confirm)
        password_form.addRow("", self.show_site_password)
        layout.addLayout(password_form)
        self.password_button = QPushButton("ثبت رمز جدید سایت")
        self.password_button.setObjectName("secondaryButton")
        self.password_button.clicked.connect(self._emit_password_reset)
        layout.addWidget(self.password_button)

        self.error = QLabel()
        self.error.setObjectName("formError")
        self.error.setWordWrap(True)
        self.error.hide()
        layout.addWidget(self.error)
        buttons = QHBoxLayout()
        self.save_button = QPushButton("ذخیره تغییرات")
        self.save_button.clicked.connect(self._emit_save)
        cancel = QPushButton("انصراف")
        cancel.setObjectName("secondaryButton")
        cancel.clicked.connect(self.reject)
        delete_button = QPushButton("حذف عضو")
        delete_button.setObjectName("dangerButton")
        delete_button.clicked.connect(self._confirm_delete)
        self.renew_button = QPushButton("تمدید عضویت")
        self.renew_button.setObjectName("renewButton")
        self.renew_button.setVisible(member.renewal_required)
        self.renew_button.clicked.connect(self._open_renewal)
        buttons.addWidget(self.save_button)
        buttons.addWidget(self.renew_button)
        buttons.addWidget(cancel)
        buttons.addStretch()
        buttons.addWidget(delete_button)
        layout.addStretch()
        outer.addWidget(scroll, 1)
        outer.addLayout(buttons)

    @staticmethod
    def _line(value):
        field = QLineEdit(str(value or ""))
        field.setClearButtonEnabled(True)
        return field

    def _emit_save(self):
        self.error.hide()
        self.save_button.setEnabled(False)
        self.save_button.setText("در حال ذخیره…")
        values = {
            "first_name": self.first_name.text(),
            "last_name": self.last_name.text(),
            "father_name": self.father_name.text(),
            "mobile": self.mobile.text(),
            "national_id": self.national_id.text(),
            "certificate_no": self.certificate_no.text(),
            "age": self.age.value() or None,
            "gender": self.gender.currentText(),
            "plan": self.plan.text(),
            "debt": self.debt.value(),
            "payment": self.payment.value(),
            "address": self.address.toPlainText().strip(),
        }
        if self.signup_time.text().strip() != self.original_signup_time:
            values["signup_time"] = self.signup_time.text()
        if self.remaining_sessions.isEnabled() and (
            self.remaining_sessions.value() != self.member.remaining_sessions
            or self.plan.text() != self.member.plan
        ):
            values["remaining_sessions"] = self.remaining_sessions.value()
        self.save_requested.emit(values)

    def _update_remaining_sessions(self, plan):
        allowance = session_allowance(plan)
        self.remaining_sessions.setEnabled(allowance is not None)
        self.remaining_sessions.setRange(-1_000_000, allowance or 0)
        self.remaining_sessions.setValue(allowance - self.member.used_sessions if allowance else 0)
        if allowance is None:
            self.remaining_sessions.setToolTip("ابتدا تعداد جلسات را در نام پلن مشخص کنید؛ مثلاً بدنسازی ۱۲ جلسه.")
        else:
            self.remaining_sessions.setToolTip("عدد منفی یعنی جلسات استفاده‌شده در مهلت تمدید.")

    def save_failed(self, message):
        self.error.setText(message)
        self.error.show()
        self.save_button.setEnabled(True)
        self.save_button.setText("ذخیره تغییرات")

    def _toggle_site_password(self, visible):
        mode = QLineEdit.EchoMode.Normal if visible else QLineEdit.EchoMode.Password
        self.site_password.setEchoMode(mode)
        self.site_password_confirm.setEchoMode(mode)

    def _emit_password_reset(self):
        self.error.hide()
        password = self.site_password.text()
        confirmation = self.site_password_confirm.text()
        if not password:
            self.password_failed("رمز جدید را وارد کنید.")
            return
        if password != confirmation:
            self.password_failed("رمز جدید و تکرار آن یکسان نیست.")
            return
        self.password_button.setEnabled(False)
        self.password_button.setText("در حال تغییر رمز…")
        self.password_reset_requested.emit(password, confirmation)

    def password_failed(self, message):
        self.error.setText(message)
        self.error.show()
        self.password_button.setEnabled(True)
        self.password_button.setText("ثبت رمز جدید سایت")

    def password_succeeded(self):
        self.site_password.clear()
        self.site_password_confirm.clear()
        self.show_site_password.setChecked(False)
        self.password_button.setEnabled(True)
        self.password_button.setText("ثبت رمز جدید سایت")

    def _confirm_delete(self):
        answer = QMessageBox.warning(
            self,
            "حذف عضو",
            f"عضو «{self.member.full_name}» حذف شود؟\n"
            "پیش از حذف یک نسخه قابل بازیابی در آرشیو Life Box ذخیره می‌شود.",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.Cancel,
            QMessageBox.StandardButton.Cancel,
        )
        if answer == QMessageBox.StandardButton.Yes:
            self.delete_requested.emit()

    def _open_renewal(self):
        dialog = RenewalDialog(self.member, self, plans=self.plans)
        dialog.submit_requested.connect(
            lambda values: self.renew_requested.emit(dialog, values)
        )
        dialog.exec()


class RenewalDialog(QDialog):
    submit_requested = pyqtSignal(object)

    def __init__(self, member, parent=None, plans=()):
        super().__init__(parent)
        self.member = member
        self.setWindowTitle("تمدید عضویت")
        self.setModal(True)
        self.resize(560, 390)
        self.setLayoutDirection(Qt.LayoutDirection.RightToLeft)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(28, 24, 28, 24)
        layout.setSpacing(16)

        title = QLabel(f"تمدید عضویت {member.full_name}")
        title.setObjectName("dialogTitle")
        layout.addWidget(title)

        carried = max(0, -(member.remaining_sessions or 0))
        explanation = QLabel(
            f"این عضو {carried} جلسه از مهلت تمدید استفاده کرده است. "
            f"این تعداد از پلن جدید کسر می‌شود و تاریخ شروع، تاریخ اولین جلسه مهلت خواهد بود."
            if carried
            else "عضو جلسه منفی ندارد؛ تاریخ شروع پلن جدید زمان همین تمدید خواهد بود."
        )
        explanation.setObjectName("membershipStatus")
        explanation.setWordWrap(True)
        layout.addWidget(explanation)

        form = QFormLayout()
        form.setSpacing(14)
        member_gender = {"مرد": "male", "زن": "female"}.get(member.gender, "all")
        self.available_plans = [
            plan
            for plan in plans
            if plan.is_active and plan.gender in {"all", member_gender}
        ]
        self.plan = QComboBox()
        self.plan.setMinimumHeight(46)
        if self.available_plans:
            for plan in self.available_plans:
                self.plan.addItem(plan.name, plan)
            current = self.plan.findText(member.plan)
            self.plan.setCurrentIndex(current if current >= 0 else 0)
        else:
            self.plan.addItem("پلن فعالی برای تمدید تعریف نشده است", None)
            self.plan.setEnabled(False)
        self.amount = QSpinBox()
        self.amount.setRange(0, 2_000_000_000)
        self.amount.setSingleStep(100_000)
        self.amount.setSuffix(" تومان")
        self.amount.setGroupSeparatorShown(True)
        self.plan.currentIndexChanged.connect(self._update_plan_price)
        self._update_plan_price(self.plan.currentIndex())
        form.addRow("پلن جدید", self.plan)
        form.addRow("مبلغ پرداخت", self.amount)
        layout.addLayout(form)

        self.error = QLabel()
        self.error.setObjectName("formError")
        self.error.setWordWrap(True)
        if self.available_plans:
            self.error.hide()
        else:
            self.error.setText(
                "برای تمدید، ابتدا یک پلن فعال و مناسب جنسیت عضو در پنل مدیریت تعریف کنید."
            )
            self.error.show()
        layout.addWidget(self.error)

        buttons = QHBoxLayout()
        self.submit = QPushButton("پرداخت و تمدید")
        self.submit.setEnabled(bool(self.available_plans))
        self.submit.clicked.connect(self._submit)
        cancel = QPushButton("انصراف")
        cancel.setObjectName("secondaryButton")
        cancel.clicked.connect(self.reject)
        buttons.addWidget(self.submit)
        buttons.addWidget(cancel)
        layout.addLayout(buttons)

    def _submit(self):
        selected_plan = self.plan.currentData()
        if selected_plan is None:
            self.error.setText("یک پلن فعال برای تمدید انتخاب کنید.")
            self.error.show()
            return
        self.error.hide()
        self.submit.setEnabled(False)
        self.submit.setText("در حال پرداخت و تمدید…")
        self.submit_requested.emit({
            "plan": selected_plan.name,
            "amount": self.amount.value(),
        })

    def _update_plan_price(self, index):
        selected_plan = self.plan.itemData(index) if index >= 0 else None
        self.amount.setValue(selected_plan.price if selected_plan is not None else 0)

    def operation_failed(self, message):
        self.error.setText(message)
        self.error.show()
        self.submit.setEnabled(True)
        self.submit.setText("پرداخت و تمدید")


class MembersPage(QWidget):
    face_index_refresh_requested = pyqtSignal()

    def __init__(self, service, pool: QThreadPool, plan_provider=None):
        super().__init__()
        self.service = service
        self.plan_provider = plan_provider
        self.pool = pool
        self.page = 1
        self.has_next = False
        self.busy = False
        self.member_ids = []
        self.search_timer = QTimer(self)
        self.search_timer.setSingleShot(True)
        self.search_timer.timeout.connect(self._new_search)
        self._build()

    def _build(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(32, 28, 32, 28)
        layout.setSpacing(16)
        header = QHBoxLayout()
        title_box = QVBoxLayout()
        title = QLabel("مدیریت اعضا")
        title.setObjectName("pageTitle")
        subtitle = QLabel("جستجو سریع و ویرایش امن اطلاعات، بدون بارگذاری تصاویر چهره")
        subtitle.setObjectName("pageSubtitle")
        title_box.addWidget(title)
        title_box.addWidget(subtitle)
        self.search = QLineEdit()
        self.search.setObjectName("searchInput")
        self.search.setPlaceholderText("نام، موبایل یا کد ملی…")
        self.search.setClearButtonEnabled(True)
        self.search.setFixedWidth(330)
        self.search.textChanged.connect(lambda: self.search_timer.start(350))
        self.search.returnPressed.connect(self._new_search)
        header.addLayout(title_box)
        header.addStretch()
        header.addWidget(self.search)
        layout.addLayout(header)

        self.notice = QLabel("در حال دریافت اعضا…")
        self.notice.setObjectName("pageNotice")
        layout.addWidget(self.notice)

        self.table = QTableWidget(0, 6)
        self.table.setHorizontalHeaderLabels(
            ["نام و نام خانوادگی", "موبایل", "کد ملی", "پلن", "باقی‌مانده", "شناسه"]
        )
        self.table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.table.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self.table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.table.setAlternatingRowColors(True)
        self.table.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.table.verticalHeader().hide()
        self.table.verticalHeader().setDefaultSectionSize(54)
        header = self.table.horizontalHeader()
        header.setSectionResizeMode(0, QHeaderView.ResizeMode.Fixed)
        header.setSectionResizeMode(1, QHeaderView.ResizeMode.Fixed)
        header.setSectionResizeMode(2, QHeaderView.ResizeMode.Fixed)
        header.setSectionResizeMode(3, QHeaderView.ResizeMode.Stretch)
        header.setSectionResizeMode(4, QHeaderView.ResizeMode.Fixed)
        self.table.setColumnWidth(0, 180)
        self.table.setColumnWidth(1, 125)
        self.table.setColumnWidth(2, 115)
        self.table.setColumnWidth(4, 88)
        self.table.setColumnHidden(5, True)
        self.table.doubleClicked.connect(self.edit_selected)
        layout.addWidget(self.table, 1)

        footer = QHBoxLayout()
        self.edit_button = QPushButton("ویرایش عضو انتخاب‌شده")
        self.edit_button.clicked.connect(self.edit_selected)
        self.edit_button.setEnabled(False)
        self.table.itemSelectionChanged.connect(
            lambda: self.edit_button.setEnabled(bool(self.table.selectedItems()) and not self.busy)
        )
        self.previous = QPushButton("صفحه قبل")
        self.previous.setObjectName("secondaryButton")
        self.previous.clicked.connect(self._previous_page)
        self.next = QPushButton("صفحه بعد")
        self.next.setObjectName("secondaryButton")
        self.next.clicked.connect(self._next_page)
        self.page_label = QLabel("صفحه ۱")
        self.page_label.setObjectName("paginationLabel")
        footer.addWidget(self.edit_button)
        footer.addStretch()
        footer.addWidget(self.next)
        footer.addWidget(self.page_label)
        footer.addWidget(self.previous)
        layout.addLayout(footer)

    def showEvent(self, event):
        super().showEvent(event)
        if not self.member_ids and not self.busy:
            self.load()

    def _new_search(self):
        self.page = 1
        self.load()

    def _previous_page(self):
        if self.page > 1:
            self.page -= 1
            self.load()

    def _next_page(self):
        if self.has_next:
            self.page += 1
            self.load()

    def load(self):
        if self.busy:
            return
        self.busy = True
        self.notice.setText("در حال دریافت اعضا…")
        self.notice.show()
        self._update_controls()
        worker = TaskWorker(
            self.service.list_members,
            self.search.text(),
            self.page,
            40,
        )
        worker.signals.succeeded.connect(self._render_page)
        worker.signals.failed.connect(self._load_failed)
        worker.signals.finished.connect(self._finish_load)
        self.pool.start(worker)

    def _render_page(self, result):
        self.has_next = result.has_next
        self.member_ids = [member.id for member in result.items]
        self.table.setRowCount(len(result.items))
        for row, member in enumerate(result.items):
            values = (
                member.full_name,
                member.mobile,
                member.national_id or "—",
                member.plan,
                str(member.remaining_sessions) if member.remaining_sessions is not None else "نامشخص",
                str(member.id),
            )
            for column, value in enumerate(values):
                item = QTableWidgetItem(value)
                item.setTextAlignment(Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignRight)
                self.table.setItem(row, column, item)
        self.notice.setText("عضوی با این مشخصات پیدا نشد." if not result.items else "")
        self.notice.setVisible(not result.items)
        self.page_label.setText(f"صفحه {result.page}")

    def _load_failed(self, message):
        self.notice.setText(f"خواندن اطلاعات انجام نشد: {message}")
        self.notice.show()

    def _finish_load(self):
        self.busy = False
        self._update_controls()

    def _update_controls(self):
        self.previous.setEnabled(not self.busy and self.page > 1)
        self.next.setEnabled(not self.busy and self.has_next)
        self.edit_button.setEnabled(not self.busy and bool(self.table.selectedItems()))

    def edit_selected(self):
        row = self.table.currentRow()
        if row < 0 or row >= len(self.member_ids) or self.busy:
            return
        self.busy = True
        self.notice.setText("در حال دریافت اطلاعات عضو…")
        self.notice.show()
        self._update_controls()
        member_id = self.member_ids[row]
        worker = TaskWorker(self._member_context, member_id)
        worker.signals.succeeded.connect(self._open_dialog)
        worker.signals.failed.connect(self._load_failed)
        worker.signals.finished.connect(self._finish_load)
        self.pool.start(worker)

    def _member_context(self, member_id):
        member = self.service.get_member(member_id)
        plans = self.plan_provider.list_plans() if self.plan_provider else ()
        return member, plans

    def _open_dialog(self, context):
        member, plans = context
        dialog = MemberDialog(member, self, plans=plans)
        dialog.save_requested.connect(
            lambda values: self._save_member(dialog, member.id, values)
        )
        dialog.delete_requested.connect(
            lambda: self._delete_member(dialog, member)
        )
        dialog.renew_requested.connect(
            lambda renewal_dialog, values: self._renew_member(
                dialog, renewal_dialog, member.id, values
            )
        )
        dialog.password_reset_requested.connect(
            lambda password, confirmation: self._reset_site_password(
                dialog, member.id, password, confirmation
            )
        )
        dialog.exec()

    def _save_member(self, dialog, member_id, values):
        worker = TaskWorker(self.service.update_member, member_id, values)
        worker.signals.succeeded.connect(lambda member: self._saved(dialog))
        worker.signals.failed.connect(dialog.save_failed)
        self.pool.start(worker)

    def _saved(self, dialog):
        dialog.accept()
        QMessageBox.information(self, "ذخیره شد", "اطلاعات عضو با موفقیت به‌روزرسانی شد.")
        self.busy = False
        self.face_index_refresh_requested.emit()
        self.load()

    def _reset_site_password(self, dialog, member_id, password, confirmation):
        worker = TaskWorker(
            self.service.reset_site_password,
            member_id,
            password,
            confirmation,
        )
        worker.signals.succeeded.connect(
            lambda result: self._site_password_reset(dialog, result)
        )
        worker.signals.failed.connect(dialog.password_failed)
        self.pool.start(worker)

    def _site_password_reset(self, dialog, result):
        dialog.password_succeeded()
        QMessageBox.information(
            dialog,
            "رمز تغییر کرد",
            f"رمز ورود سایت برای شماره {result.get('mobile', 'عضو')} با موفقیت تغییر کرد.",
        )

    def _renew_member(self, member_dialog, renewal_dialog, member_id, values):
        worker = TaskWorker(
            self.service.renew_member,
            member_id,
            values["plan"],
            values["amount"],
        )
        worker.signals.succeeded.connect(
            lambda result: self._membership_renewed(
                member_dialog, renewal_dialog, result
            )
        )
        worker.signals.failed.connect(renewal_dialog.operation_failed)
        self.pool.start(worker)

    def _membership_renewed(self, member_dialog, renewal_dialog, result):
        renewal_dialog.accept()
        member_dialog.accept()
        QMessageBox.information(
            self,
            "عضویت تمدید شد",
            f"عضویت با موفقیت تمدید شد.\n"
            f"{result.carried_sessions} جلسه مهلت از پلن جدید کسر شد.\n"
            f"جلسات باقی‌مانده: {result.member.remaining_sessions}\n"
            f"شروع پلن: {result.membership_started_at}\n"
            f"رسید پرداخت: {result.payment_reference}",
        )
        self.busy = False
        self.load()

    def _delete_member(self, dialog, member):
        worker = TaskWorker(self.service.delete_member, member.id)
        worker.signals.succeeded.connect(
            lambda payload: self._member_deleted(dialog, member)
        )
        worker.signals.failed.connect(dialog.save_failed)
        self.pool.start(worker)

    def _member_deleted(self, dialog, member):
        dialog.accept()
        self.face_index_refresh_requested.emit()
        QMessageBox.information(
            self,
            "عضو حذف شد",
            f"{member.full_name} حذف و نسخه پشتیبان او در آرشیو ذخیره شد.",
        )
        self.busy = False
        self.load()
