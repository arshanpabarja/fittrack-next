from PyQt6.QtCore import Qt, QThreadPool, QTimer
from PyQt6.QtWidgets import (
    QAbstractItemView,
    QHeaderView,
    QLabel,
    QMessageBox,
    QPushButton,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from app.ui.workers import TaskWorker


STATUS_LABELS = {
    "payment_pending": "وضعیت POS نامشخص؛ نیازمند بررسی رسید",
    "payment_approved": "پرداخت تأییدشده؛ آماده بازیابی",
    "member_updated": "عضویت تمدیدشده؛ تاریخچه در انتظار",
}


class RenewalRecoveryPage(QWidget):
    def __init__(self, member_service, pool: QThreadPool):
        super().__init__()
        self.member_service = member_service
        self.pool = pool
        self.busy = False
        self._build()

    def _build(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(32, 28, 32, 32)
        layout.setSpacing(16)
        title = QLabel("پرداخت‌ها و تمدیدهای ناقص")
        title.setObjectName("pageTitle")
        subtitle = QLabel(
            "بازیابی امن هیچ‌وقت کارتخوان را دوباره فراخوانی نمی‌کند. موارد با وضعیت نامشخص POS باید ابتدا با رسید دستگاه تطبیق داده شوند."
        )
        subtitle.setObjectName("pageSubtitle")
        subtitle.setWordWrap(True)
        layout.addWidget(title)
        layout.addWidget(subtitle)
        self.notice = QLabel()
        self.notice.setObjectName("pageNotice")
        layout.addWidget(self.notice)
        self.table = QTableWidget(0, 7)
        self.table.setHorizontalHeaderLabels(
            ["زمان", "عضو", "پلن جدید", "مبلغ", "مرجع", "وضعیت", "آخرین خطا"]
        )
        self.table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.table.verticalHeader().hide()
        self.table.horizontalHeader().setSectionResizeMode(2, QHeaderView.ResizeMode.Stretch)
        self.table.horizontalHeader().setSectionResizeMode(5, QHeaderView.ResizeMode.Stretch)
        layout.addWidget(self.table, 1)
        self.recover = QPushButton("تلاش برای بازیابی امن")
        self.recover.clicked.connect(self._recover)
        layout.addWidget(self.recover)

    def showEvent(self, event):
        super().showEvent(event)
        QTimer.singleShot(0, self.refresh)

    def refresh(self):
        if self.busy:
            return
        self.busy = True
        worker = TaskWorker(self.member_service.incomplete_renewals)
        worker.signals.succeeded.connect(self._render)
        worker.signals.failed.connect(self.notice.setText)
        worker.signals.finished.connect(lambda: setattr(self, "busy", False))
        self.pool.start(worker)

    def _render(self, rows):
        rows = list(rows)
        self.table.setRowCount(len(rows))
        for row, item in enumerate(rows):
            values = (
                item["created_at"],
                str(item["member_id"]),
                item["new_plan"],
                f"{item['requested_amount']:,} تومان",
                item["payment_reference"] or "—",
                STATUS_LABELS.get(item["status"], item["status"]),
                item["last_error"] or "—",
            )
            for column, value in enumerate(values):
                cell = QTableWidgetItem(str(value))
                cell.setTextAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
                self.table.setItem(row, column, cell)
        self.notice.setText("مورد ناقصی وجود ندارد." if not rows else f"{len(rows)} مورد نیازمند بررسی است.")

    def _recover(self):
        if self.busy:
            return
        self.busy = True
        self.recover.setEnabled(False)
        worker = TaskWorker(self.member_service.recover_incomplete_renewals)
        worker.signals.succeeded.connect(self._recovered)
        worker.signals.failed.connect(self.notice.setText)
        worker.signals.finished.connect(self._finished)
        self.pool.start(worker)

    def _recovered(self, count):
        QMessageBox.information(
            self,
            "بازیابی تمدیدها",
            f"{count} تمدید بدون برداشت مجدد از کارت بازیابی شد.",
        )

    def _finished(self):
        self.busy = False
        self.recover.setEnabled(True)
        self.refresh()
