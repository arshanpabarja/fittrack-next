from PyQt6.QtCore import Qt, QThreadPool, pyqtSignal
from PyQt6.QtGui import QPixmap
from PyQt6.QtWidgets import (
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QScrollArea,
    QVBoxLayout,
    QWidget,
)

from app.ui.widgets import StatCard, TouchCard
from app.ui.workers import TaskWorker


class DashboardPage(QWidget):
    action_requested = pyqtSignal(str)

    def __init__(self, service, pool: QThreadPool, qr_path=None, signup_url=""):
        super().__init__()
        self.service = service
        self.pool = pool
        self.qr_path = qr_path
        self.signup_url = signup_url
        self.loaded = False
        self.busy = False
        self.cards = {}
        self._build()

    def _build(self):
        root_layout = QVBoxLayout(self)
        root_layout.setContentsMargins(0, 0, 0, 0)
        root_layout.setSpacing(0)
        scroll = QScrollArea()
        scroll.setObjectName("dashboardScroll")
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.Shape.NoFrame)
        content = QWidget()
        content.setObjectName("dashboardContent")
        layout = QVBoxLayout(content)
        layout.setContentsMargins(32, 28, 32, 28)
        layout.setSpacing(20)
        header = QHBoxLayout()
        title_box = QVBoxLayout()
        title = QLabel("داشبورد پذیرش")
        title.setObjectName("pageTitle")
        subtitle = QLabel("امور روزانه باشگاه را سریع و بدون توقف مدیریت کنید.")
        subtitle.setObjectName("pageSubtitle")
        title_box.addWidget(title)
        title_box.addWidget(subtitle)
        self.refresh_button = QPushButton("به‌روزرسانی")
        self.refresh_button.setObjectName("secondaryButton")
        self.refresh_button.clicked.connect(self.refresh)
        header.addLayout(title_box)
        header.addStretch()
        header.addWidget(self.refresh_button)
        layout.addLayout(header)

        stats = QGridLayout()
        stats.setSpacing(12)
        for index, (key, label, symbol) in enumerate((
            ("inside", "افراد حاضر", "●"),
            ("today_entries", "ورودی امروز", "↳"),
            ("members", "کل اعضا", "◉"),
        )):
            card = StatCard(label, symbol)
            self.cards[key] = card
            stats.addWidget(card, 0, index)
        layout.addLayout(stats)

        section = QLabel("عملیات اصلی")
        section.setObjectName("sectionTitle")
        layout.addWidget(section)
        actions = QGridLayout()
        actions.setSpacing(14)
        specs = (
            ("attendance", "ورود اعضا", "تشخیص خودکار چهره و تخصیص کمد", "→", True),
            ("walk_in", "ثبت‌نام حضوری", "انتخاب پلن و ساخت عضویت داخل باشگاه", "+", False),
            ("pending", "پذیرش کاربر از سایت", "اسکن خودکار چهره، پرداخت و فعال‌سازی", "↻", False),
            ("members", "مدیریت اعضا", "جستجو و ویرایش اطلاعات", "◉", False),
            ("coaches", "دسترسی مربیان سایت", "ساخت رمز ورود و تعیین پلن‌های مجاز", "◆", False),
            ("reports", "گزارش‌ها", "بررسی ورودها، خروج‌ها و وضعیت کمدها", "▥", False),
        )
        for index, spec in enumerate(specs):
            key, title, description, symbol, primary = spec
            card = TouchCard("primaryAction" if primary else "actionCard")
            card.setFixedHeight(230)
            card.clicked.connect(
                lambda page=key: self.action_requested.emit(page)
            )
            card_layout = QVBoxLayout(card)
            card_layout.setContentsMargins(24, 22, 24, 22)
            icon = QLabel(symbol)
            icon.setObjectName("actionIcon")
            icon.setFixedSize(48, 48)
            icon.setAlignment(Qt.AlignmentFlag.AlignCenter)
            heading = QLabel(title)
            heading.setObjectName("actionTitle")
            detail = QLabel(description)
            detail.setObjectName("actionDescription")
            open_label = QLabel("لمس برای باز کردن  ←")
            open_label.setObjectName("actionLink")
            card_layout.addWidget(icon, alignment=Qt.AlignmentFlag.AlignRight)
            card_layout.addWidget(heading)
            card_layout.addWidget(detail)
            card_layout.addStretch()
            card_layout.addWidget(open_label, alignment=Qt.AlignmentFlag.AlignLeft)
            card.make_children_transparent()
            actions.addWidget(card, index // 3, index % 3)
        layout.addLayout(actions)
        layout.addSpacing(44)

        qr_row = QHBoxLayout()
        qr_row.setContentsMargins(0, 0, 0, 0)
        qr_row.addStretch()
        qr_row.addWidget(self._signup_qr_card())
        qr_row.addStretch()
        layout.addLayout(qr_row)
        layout.addStretch()
        scroll.setWidget(content)
        root_layout.addWidget(scroll)

    def _signup_qr_card(self):
        card = QFrame()
        card.setObjectName("signupQrCard")
        card.setFixedSize(540, 330)
        card_layout = QVBoxLayout(card)
        card_layout.setContentsMargins(30, 22, 30, 22)
        card_layout.setSpacing(7)

        title = QLabel("ثبت‌نام آنلاین")
        title.setObjectName("signupQrTitle")
        title.setAlignment(Qt.AlignmentFlag.AlignCenter)
        hint = QLabel("برای ساخت حساب، QR را با موبایل اسکن کنید")
        hint.setObjectName("signupQrHint")
        hint.setAlignment(Qt.AlignmentFlag.AlignCenter)

        qr = QLabel()
        qr.setObjectName("signupQrImage")
        qr.setFixedSize(188, 188)
        qr.setAlignment(Qt.AlignmentFlag.AlignCenter)
        pixmap = QPixmap(str(self.qr_path)) if self.qr_path else QPixmap()
        if not pixmap.isNull():
            qr.setPixmap(
                pixmap.scaled(
                    176,
                    176,
                    Qt.AspectRatioMode.KeepAspectRatio,
                    Qt.TransformationMode.SmoothTransformation,
                )
            )
        else:
            qr.setText("QR")

        address = QLabel(self.signup_url.removeprefix("http://").removeprefix("https://"))
        address.setObjectName("signupQrAddress")
        address.setAlignment(Qt.AlignmentFlag.AlignCenter)
        address.setLayoutDirection(Qt.LayoutDirection.LeftToRight)

        card_layout.addWidget(title)
        card_layout.addWidget(hint)
        card_layout.addWidget(qr, alignment=Qt.AlignmentFlag.AlignCenter)
        card_layout.addWidget(address)
        return card

    def showEvent(self, event):
        super().showEvent(event)
        if not self.loaded:
            self.refresh()

    def refresh(self):
        if self.busy:
            return
        self.busy = True
        self.refresh_button.setEnabled(False)
        self.refresh_button.setText("در حال خواندن…")
        worker = TaskWorker(self.service.load)
        worker.signals.succeeded.connect(self._apply_stats)
        worker.signals.failed.connect(self._show_error)
        worker.signals.finished.connect(self._finish_refresh)
        self.pool.start(worker)

    def _apply_stats(self, stats):
        self.loaded = True
        for key, card in self.cards.items():
            card.set_value(getattr(stats, key))

    def _show_error(self, message):
        for card in self.cards.values():
            card.set_value(None)

    def _finish_refresh(self):
        self.busy = False
        self.refresh_button.setEnabled(True)
        self.refresh_button.setText("به‌روزرسانی")
