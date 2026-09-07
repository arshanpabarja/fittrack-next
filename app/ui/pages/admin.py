from PyQt6.QtCore import Qt, QThreadPool, pyqtSignal
from PyQt6.QtWidgets import (
    QAbstractItemView,
    QCheckBox,
    QComboBox,
    QDialog,
    QFrame,
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
    QVBoxLayout,
    QWidget,
)

from app.ui.widgets import StatCard
from app.ui.workers import TaskWorker


GENDER_LABELS = {"all": "همه", "male": "مرد", "female": "زن"}


class PlanDialog(QDialog):
    save_requested = pyqtSignal(object)

    def __init__(self, plan=None, parent=None):
        super().__init__(parent)
        self.plan = plan
        self.setWindowTitle("ویرایش پلن" if plan else "ساخت پلن جدید")
        self.setModal(True)
        self.setFixedWidth(560)
        self.setLayoutDirection(Qt.LayoutDirection.RightToLeft)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(28, 26, 28, 26)
        layout.setSpacing(10)

        title = QLabel("ویرایش پلن عضویت" if plan else "پلن عضویت جدید")
        title.setObjectName("dialogTitle")
        hint = QLabel(
            "این تغییر مستقیماً در فهرست پلن‌های باشگاه ذخیره می‌شود و در ثبت‌نام حضوری و تمدید قابل انتخاب است."
        )
        hint.setObjectName("pageSubtitle")
        hint.setWordWrap(True)
        layout.addWidget(title)
        layout.addWidget(hint)
        layout.addSpacing(8)

        layout.addWidget(QLabel("نام کامل پلن"))
        self.name = QLineEdit(plan.name if plan else "")
        self.name.setPlaceholderText("مثلاً بدنسازی ۱۲ جلسه در ماه")
        layout.addWidget(self.name)

        layout.addWidget(QLabel("مناسب برای"))
        self.gender = QComboBox()
        for value, label in GENDER_LABELS.items():
            self.gender.addItem(label, value)
        if plan:
            self.gender.setCurrentIndex(max(0, self.gender.findData(plan.gender)))
        layout.addWidget(self.gender)

        layout.addWidget(QLabel("تعداد جلسات در ماه"))
        self.sessions = QSpinBox()
        self.sessions.setRange(1, 60)
        self.sessions.setValue(plan.sessions_per_month if plan and plan.sessions_per_month else 12)
        layout.addWidget(self.sessions)

        layout.addWidget(QLabel("مبلغ پلن (تومان)"))
        self.price = QSpinBox()
        self.price.setRange(0, 2_000_000_000)
        self.price.setSingleStep(100_000)
        self.price.setValue(plan.price if plan else 0)
        self.price.setGroupSeparatorShown(True)
        layout.addWidget(self.price)

        self.active = QCheckBox("پلن برای ثبت‌نام فعال باشد")
        self.active.setChecked(plan.is_active if plan else True)
        layout.addWidget(self.active)

        self.error = QLabel()
        self.error.setObjectName("formError")
        self.error.setWordWrap(True)
        self.error.hide()
        layout.addWidget(self.error)
        actions = QHBoxLayout()
        self.save_button = QPushButton("ذخیره پلن")
        self.save_button.clicked.connect(self._submit)
        cancel = QPushButton("انصراف")
        cancel.setObjectName("secondaryButton")
        cancel.clicked.connect(self.reject)
        actions.addWidget(self.save_button)
        actions.addWidget(cancel)
        layout.addLayout(actions)

    def _submit(self):
        self.error.hide()
        self.save_button.setEnabled(False)
        self.save_button.setText("در حال ذخیره…")
        self.save_requested.emit({
            "name": self.name.text(),
            "gender": self.gender.currentData(),
            "sessions_per_month": self.sessions.value(),
            "price": self.price.value(),
            "is_active": self.active.isChecked(),
        })

    def operation_failed(self, message):
        self.error.setText(message)
        self.error.show()
        self.save_button.setEnabled(True)
        self.save_button.setText("ذخیره پلن")


class AdminPanelPage(QWidget):
    navigation_requested = pyqtSignal(str)
    plans_changed = pyqtSignal()

    def __init__(self, reports_service, plans_service, pool: QThreadPool):
        super().__init__()
        self.reports_service = reports_service
        self.plans_service = plans_service
        self.pool = pool
        self.plans = []
        self.activity_busy = False
        self.plans_busy = False
        self._build()

    def _build(self):
        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        scroll = QScrollArea()
        scroll.setFrameShape(QFrame.Shape.NoFrame)
        scroll.setWidgetResizable(True)
        content = QWidget()
        layout = QVBoxLayout(content)
        layout.setContentsMargins(32, 28, 32, 36)
        layout.setSpacing(18)

        header = QHBoxLayout()
        copy = QVBoxLayout()
        title = QLabel("پنل مدیریت")
        title.setObjectName("pageTitle")
        subtitle = QLabel("گزارش تردد، پلن‌های عضویت و دسترسی مربیان را از یک محل مدیریت کنید.")
        subtitle.setObjectName("pageSubtitle")
        copy.addWidget(title)
        copy.addWidget(subtitle)
        coaches = QPushButton("مدیریت دسترسی مربیان  ←")
        coaches.setObjectName("secondaryButton")
        coaches.clicked.connect(lambda: self.navigation_requested.emit("coaches"))
        header.addLayout(copy)
        header.addStretch()
        header.addWidget(coaches)
        layout.addLayout(header)

        metrics = QHBoxLayout()
        self.today_card = StatCard("ورودی امروز", "↳")
        self.month_card = StatCard("ورودی این ماه", "▥")
        self.inside_card = StatCard("افراد حاضر", "●")
        metrics.addWidget(self.today_card)
        metrics.addWidget(self.month_card)
        metrics.addWidget(self.inside_card)
        layout.addLayout(metrics)

        activity_head = QHBoxLayout()
        activity_title = QLabel("ورود اعضا")
        activity_title.setObjectName("sectionTitle")
        self.period = QComboBox()
        self.period.addItem("امروز", "today")
        self.period.addItem("این ماه", "month")
        self.period.setFixedWidth(170)
        self.period.currentIndexChanged.connect(self.refresh_activity)
        activity_head.addWidget(activity_title)
        activity_head.addStretch()
        activity_head.addWidget(self.period)
        layout.addLayout(activity_head)
        self.activity_notice = QLabel()
        self.activity_notice.setObjectName("pageNotice")
        layout.addWidget(self.activity_notice)
        self.activity_table = QTableWidget(0, 6)
        self.activity_table.setMinimumHeight(330)
        self.activity_table.setHorizontalHeaderLabels(
            ["نام عضو", "موبایل", "پلن", "زمان ورود", "وضعیت خروج", "کمد"]
        )
        self.activity_table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.activity_table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.activity_table.verticalHeader().hide()
        self.activity_table.verticalHeader().setDefaultSectionSize(56)
        self.activity_table.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
        for column in range(1, 6):
            self.activity_table.horizontalHeader().setSectionResizeMode(column, QHeaderView.ResizeMode.ResizeToContents)
        layout.addWidget(self.activity_table)

        plan_head = QHBoxLayout()
        plan_title = QLabel("پلن‌های باشگاه و ثبت‌نام حضوری")
        plan_title.setObjectName("sectionTitle")
        add_plan = QPushButton("+  ساخت پلن جدید")
        add_plan.clicked.connect(lambda: self._open_plan(None))
        edit_plan = QPushButton("ویرایش پلن انتخاب‌شده")
        edit_plan.setObjectName("secondaryButton")
        edit_plan.clicked.connect(self._edit_selected_plan)
        plan_head.addWidget(plan_title)
        plan_head.addStretch()
        plan_head.addWidget(edit_plan)
        plan_head.addWidget(add_plan)
        layout.addLayout(plan_head)
        self.plan_notice = QLabel()
        self.plan_notice.setObjectName("pageNotice")
        layout.addWidget(self.plan_notice)
        self.plan_table = QTableWidget(0, 6)
        self.plan_table.setMinimumHeight(390)
        self.plan_table.setHorizontalHeaderLabels(
            ["نام پلن", "گروه", "جلسات ماهانه", "مبلغ", "وضعیت", "شناسه"]
        )
        self.plan_table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.plan_table.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self.plan_table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.plan_table.verticalHeader().hide()
        self.plan_table.verticalHeader().setDefaultSectionSize(58)
        self.plan_table.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
        for column in range(1, 5):
            self.plan_table.horizontalHeader().setSectionResizeMode(column, QHeaderView.ResizeMode.ResizeToContents)
        self.plan_table.setColumnHidden(5, True)
        self.plan_table.doubleClicked.connect(self._edit_selected_plan)
        layout.addWidget(self.plan_table)
        scroll.setWidget(content)
        root.addWidget(scroll)

    def showEvent(self, event):
        super().showEvent(event)
        self.refresh_activity()
        self.refresh_plans()

    def refresh_activity(self):
        if self.activity_busy:
            return
        self.activity_busy = True
        self.activity_notice.setText("در حال خواندن ترددها…")
        worker = TaskWorker(self.reports_service.activity_overview, self.period.currentData())
        worker.signals.succeeded.connect(self._render_activity)
        worker.signals.failed.connect(lambda message: self.activity_notice.setText(message))
        worker.signals.finished.connect(lambda: setattr(self, "activity_busy", False))
        self.pool.start(worker)

    def _render_activity(self, result):
        self.today_card.set_value(result["today_entries"])
        self.month_card.set_value(result["month_entries"])
        self.inside_card.set_value(result["inside"])
        items = result["items"]
        self.activity_table.setRowCount(len(items))
        for row, item in enumerate(items):
            checkout = item.checked_out_at or "داخل باشگاه"
            values = (item.full_name, item.mobile, item.plan, item.checked_in_at, checkout, str(item.locker_id or "—"))
            for column, value in enumerate(values):
                cell = QTableWidgetItem(value)
                cell.setTextAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
                self.activity_table.setItem(row, column, cell)
        self.activity_notice.setText("ترددی در این بازه ثبت نشده است." if not items else "")

    def refresh_plans(self):
        if self.plans_busy:
            return
        self.plans_busy = True
        self.plan_notice.setText("در حال خواندن پلن‌های فعال از دیتابیس محلی…")
        worker = TaskWorker(self.plans_service.load)
        worker.signals.succeeded.connect(self._render_plans)
        worker.signals.failed.connect(lambda message: self.plan_notice.setText(message))
        worker.signals.finished.connect(lambda: setattr(self, "plans_busy", False))
        self.pool.start(worker)

    def _render_plans(self, plans):
        self.plans = list(plans)
        self.plan_table.setRowCount(len(self.plans))
        for row, plan in enumerate(self.plans):
            values = (
                plan.name,
                GENDER_LABELS.get(plan.gender, plan.gender),
                str(plan.sessions_per_month),
                f"{plan.price:,} تومان",
                "فعال" if plan.is_active else "غیرفعال",
                str(plan.id),
            )
            for column, value in enumerate(values):
                cell = QTableWidgetItem(value)
                cell.setTextAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
                self.plan_table.setItem(row, column, cell)
        self.plan_notice.setText("پلنی ساخته نشده است." if not self.plans else "")

    def _selected_plan(self):
        row = self.plan_table.currentRow()
        return self.plans[row] if 0 <= row < len(self.plans) else None

    def _edit_selected_plan(self):
        plan = self._selected_plan()
        if plan:
            self._open_plan(plan)
        else:
            QMessageBox.information(self, "انتخاب پلن", "ابتدا یک پلن را از جدول انتخاب کنید.")

    def _open_plan(self, plan):
        dialog = PlanDialog(plan, self)
        dialog.save_requested.connect(lambda values: self._save_plan(dialog, plan, values))
        dialog.exec()

    def _save_plan(self, dialog, plan, values):
        worker = TaskWorker(self.plans_service.save, values, plan.id if plan else None)
        worker.signals.succeeded.connect(lambda saved: self._plan_saved(dialog, saved))
        worker.signals.failed.connect(dialog.operation_failed)
        self.pool.start(worker)

    def _plan_saved(self, dialog, plan):
        dialog.accept()
        self.plans_changed.emit()
        QMessageBox.information(
            self,
            "پلن ذخیره شد",
            f"پلن «{plan.name}» در فهرست محلی Life Box ذخیره شد.",
        )
        self.refresh_plans()
