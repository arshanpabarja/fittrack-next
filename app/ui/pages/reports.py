from PyQt6.QtCore import Qt, QThreadPool
from PyQt6.QtWidgets import (
    QAbstractItemView,
    QFileDialog,
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


class ReportsPage(QWidget):
    def __init__(self, service, pool: QThreadPool):
        super().__init__()
        self.service = service
        self.pool = pool
        self.page = 1
        self.has_next = False
        self.busy = False
        self.loaded = False
        self._build()

    def _build(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(32, 28, 32, 28)
        layout.setSpacing(16)
        header = QHBoxLayout()
        copy = QVBoxLayout()
        title = QLabel("گزارش تردد")
        title.setObjectName("pageTitle")
        subtitle = QLabel("سوابق سریع نسخه جدید؛ تاریخچه قدیمی بدون تغییر آرشیو شده است.")
        subtitle.setObjectName("pageSubtitle")
        copy.addWidget(title)
        copy.addWidget(subtitle)
        self.search = QLineEdit()
        self.search.setPlaceholderText("نام یا موبایل")
        self.search.setFixedWidth(260)
        self.search.returnPressed.connect(self.new_search)
        search_button = QPushButton("جستجو")
        search_button.clicked.connect(self.new_search)
        export = QPushButton("خروجی CSV")
        export.setObjectName("secondaryButton")
        export.clicked.connect(self.export_csv)
        header.addLayout(copy)
        header.addStretch()
        header.addWidget(self.search)
        header.addWidget(search_button)
        header.addWidget(export)
        layout.addLayout(header)
        self.notice = QLabel()
        self.notice.setObjectName("pageNotice")
        layout.addWidget(self.notice)
        self.table = QTableWidget(0, 7)
        self.table.setHorizontalHeaderLabels(
            ["نام", "موبایل", "پلن", "زمان ورود", "زمان خروج", "کمد", "شناسه"]
        )
        self.table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.table.setAlternatingRowColors(True)
        self.table.verticalHeader().hide()
        self.table.verticalHeader().setDefaultSectionSize(54)
        self.table.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
        for column in range(1, 6):
            self.table.horizontalHeader().setSectionResizeMode(column, QHeaderView.ResizeMode.ResizeToContents)
        self.table.setColumnHidden(6, True)
        layout.addWidget(self.table, 1)
        footer = QHBoxLayout()
        self.previous = QPushButton("صفحه قبل")
        self.previous.setObjectName("secondaryButton")
        self.previous.clicked.connect(self.previous_page)
        self.next = QPushButton("صفحه بعد")
        self.next.setObjectName("secondaryButton")
        self.next.clicked.connect(self.next_page)
        self.page_label = QLabel("صفحه ۱")
        footer.addStretch()
        footer.addWidget(self.next)
        footer.addWidget(self.page_label)
        footer.addWidget(self.previous)
        layout.addLayout(footer)

    def showEvent(self, event):
        super().showEvent(event)
        if not self.loaded:
            self.load()

    def new_search(self):
        self.page = 1
        self.load()

    def previous_page(self):
        if self.page > 1:
            self.page -= 1
            self.load()

    def next_page(self):
        if self.has_next:
            self.page += 1
            self.load()

    def load(self):
        if self.busy:
            return
        self.busy = True
        self.notice.setText("در حال خواندن گزارش…")
        self._controls()
        worker = TaskWorker(
            self.service.list_sessions,
            self.search.text(),
            self.page,
            50,
        )
        worker.signals.succeeded.connect(self._render)
        worker.signals.failed.connect(lambda message: self.notice.setText(message))
        worker.signals.finished.connect(self._finished)
        self.pool.start(worker)

    def _render(self, result):
        self.loaded = True
        self.has_next = result.has_next
        self.table.setRowCount(len(result.items))
        for row, item in enumerate(result.items):
            values = (
                item.full_name,
                item.mobile,
                item.plan,
                item.checked_in_at,
                item.checked_out_at or "داخل باشگاه",
                str(item.locker_id or "—"),
                str(item.id),
            )
            for column, value in enumerate(values):
                cell = QTableWidgetItem(value)
                cell.setTextAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
                self.table.setItem(row, column, cell)
        self.notice.setText("رکوردی ثبت نشده است." if not result.items else "")
        self.page_label.setText(f"صفحه {result.page}")

    def _finished(self):
        self.busy = False
        self._controls()

    def _controls(self):
        self.previous.setEnabled(not self.busy and self.page > 1)
        self.next.setEnabled(not self.busy and self.has_next)

    def export_csv(self):
        path, _ = QFileDialog.getSaveFileName(
            self,
            "ذخیره گزارش",
            "fittrack-attendance.csv",
            "CSV (*.csv)",
        )
        if not path:
            return
        worker = TaskWorker(self.service.export_csv, path)
        worker.signals.succeeded.connect(
            lambda count: QMessageBox.information(
                self, "خروجی آماده شد", f"{count} رکورد در فایل ذخیره شد."
            )
        )
        worker.signals.failed.connect(
            lambda message: QMessageBox.warning(self, "خطا", message)
        )
        self.pool.start(worker)
