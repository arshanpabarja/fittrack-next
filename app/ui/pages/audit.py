import json

from PyQt6.QtCore import Qt, QThreadPool, QTimer
from PyQt6.QtWidgets import (
    QAbstractItemView,
    QComboBox,
    QFrame,
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

from app.services.audit import ACTION_LABELS
from app.ui.workers import TaskWorker


def _pretty(value):
    try:
        parsed = json.loads(value or "{}")
    except (TypeError, ValueError):
        return str(value or "—")
    if not parsed:
        return "—"
    return json.dumps(parsed, ensure_ascii=False, indent=2, sort_keys=True)


class ManagerAuditPage(QWidget):
    def __init__(self, audit_service, pool: QThreadPool):
        super().__init__()
        self.audit_service = audit_service
        self.pool = pool
        self.items = []
        self.busy = False
        self._build()

    def _build(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(32, 28, 32, 32)
        layout.setSpacing(16)

        title = QLabel("تاریخچه فعالیت مدیران")
        title.setObjectName("pageTitle")
        subtitle = QLabel(
            "ورود مدیران و تغییرات مهم اعضا، تمدیدها و پلن‌ها در این بخش به‌صورت غیرقابل‌ویرایش ثبت می‌شود."
        )
        subtitle.setObjectName("pageSubtitle")
        subtitle.setWordWrap(True)
        layout.addWidget(title)
        layout.addWidget(subtitle)

        filters = QHBoxLayout()
        self.search = QLineEdit()
        self.search.setPlaceholderText("جست‌وجوی مدیر، عضو، شناسه یا خطا…")
        self.search.setClearButtonEnabled(True)
        self.search.returnPressed.connect(self.refresh)
        self.action = QComboBox()
        self.action.addItem("همه فعالیت‌ها", "")
        for value, label in ACTION_LABELS.items():
            self.action.addItem(label, value)
        self.action.currentIndexChanged.connect(self.refresh)
        refresh = QPushButton("به‌روزرسانی")
        refresh.setObjectName("secondaryButton")
        refresh.clicked.connect(self.refresh)
        filters.addWidget(self.search, 1)
        filters.addWidget(self.action)
        filters.addWidget(refresh)
        layout.addLayout(filters)

        self.notice = QLabel()
        self.notice.setObjectName("pageNotice")
        layout.addWidget(self.notice)

        self.table = QTableWidget(0, 6)
        self.table.setHorizontalHeaderLabels(
            ["زمان", "مدیر", "فعالیت", "شرح", "وضعیت", "شناسه"]
        )
        self.table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.table.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self.table.verticalHeader().hide()
        self.table.verticalHeader().setDefaultSectionSize(54)
        self.table.horizontalHeader().setSectionResizeMode(3, QHeaderView.ResizeMode.Stretch)
        for column in (0, 1, 2, 4):
            self.table.horizontalHeader().setSectionResizeMode(
                column, QHeaderView.ResizeMode.ResizeToContents
            )
        self.table.setColumnHidden(5, True)
        self.table.doubleClicked.connect(self._show_details)
        layout.addWidget(self.table, 1)

        hint = QLabel("برای دیدن مقدار قبل و بعد، روی هر ردیف دوبار کلیک کنید.")
        hint.setObjectName("pageSubtitle")
        layout.addWidget(hint)

    def showEvent(self, event):
        super().showEvent(event)
        QTimer.singleShot(0, self.refresh)

    def refresh(self):
        if self.busy:
            return
        self.busy = True
        self.notice.setText("در حال خواندن تاریخچه…")
        worker = TaskWorker(
            self.audit_service.list_activity,
            self.search.text(),
            self.action.currentData(),
        )
        worker.signals.succeeded.connect(self._render)
        worker.signals.failed.connect(self.notice.setText)
        worker.signals.finished.connect(lambda: setattr(self, "busy", False))
        self.pool.start(worker)

    def _render(self, rows):
        self.items = list(rows)
        self.table.setRowCount(len(self.items))
        for row, item in enumerate(self.items):
            values = (
                item["created_at"],
                item["actor"],
                ACTION_LABELS.get(item["action"], item["action"]),
                item["summary"] or "—",
                "موفق" if item["success"] else "ناموفق",
                str(item["id"]),
            )
            for column, value in enumerate(values):
                cell = QTableWidgetItem(str(value))
                cell.setTextAlignment(
                    Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter
                )
                self.table.setItem(row, column, cell)
        self.notice.setText("فعالیتی پیدا نشد." if not self.items else "")

    def _show_details(self):
        row = self.table.currentRow()
        if not 0 <= row < len(self.items):
            return
        item = self.items[row]
        message = (
            f"مدیر: {item['actor']}\n"
            f"فعالیت: {ACTION_LABELS.get(item['action'], item['action'])}\n"
            f"زمان: {item['created_at']}\n"
            f"شرح: {item['summary'] or '—'}\n\n"
            f"قبل از تغییر:\n{_pretty(item['before_json'])}\n\n"
            f"بعد از تغییر:\n{_pretty(item['after_json'])}"
        )
        if item["error"]:
            message += f"\n\nخطا:\n{item['error']}"
        box = QMessageBox(self)
        box.setWindowTitle("جزئیات فعالیت")
        box.setText(message)
        box.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        box.exec()
