from datetime import datetime

from PyQt6.QtCore import Qt, QThreadPool, QTimer, pyqtSignal
from PyQt6.QtGui import QColor, QPixmap
from PyQt6.QtWidgets import (
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QGraphicsDropShadowEffect,
    QScrollArea,
    QSizePolicy,
    QVBoxLayout,
    QWidget,
)

from app.ui.widgets import TouchCard, to_persian_digits
from app.ui.workers import TaskWorker


class DashboardPage(QWidget):
    """Public, touch-first home screen for gym members."""

    action_requested = pyqtSignal(str)

    WEEKDAYS = (
        "دوشنبه",
        "سه‌شنبه",
        "چهارشنبه",
        "پنج‌شنبه",
        "جمعه",
        "شنبه",
        "یکشنبه",
    )

    def __init__(self, service, pool: QThreadPool, qr_path=None, signup_url=""):
        super().__init__()
        # The main window is RTL for Persian forms. The kiosk composition has
        # deliberate physical left/right placement and must not be mirrored.
        self.setLayoutDirection(Qt.LayoutDirection.LeftToRight)
        self.service = service
        self.pool = pool
        self.qr_path = qr_path
        self.signup_url = signup_url
        self.loaded = False
        self.busy = False
        self._build()

        self.clock_timer = QTimer(self)
        self.clock_timer.timeout.connect(self._update_clock)
        self.clock_timer.start(30_000)
        self._update_clock()

        self.refresh_timer = QTimer(self)
        self.refresh_timer.timeout.connect(self._refresh_if_visible)
        self.refresh_timer.start(30_000)

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
        outer = QVBoxLayout(content)
        outer.setContentsMargins(36, 28, 36, 28)
        outer.setSpacing(0)
        outer.addStretch(1)

        shell = QWidget()
        shell.setObjectName("kioskShell")
        shell.setMaximumWidth(1080)
        shell.setMinimumHeight(1700)
        shell.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        layout = QVBoxLayout(shell)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(24)
        layout.addLayout(self._header())
        welcome_row = QHBoxLayout()
        welcome_row.setDirection(QHBoxLayout.Direction.LeftToRight)
        welcome_row.addStretch(1)
        welcome_row.addWidget(self._welcome_block())
        layout.addLayout(welcome_row)
        layout.addWidget(self._primary_action())

        secondary = QGridLayout()
        secondary.setHorizontalSpacing(18)
        secondary.setVerticalSpacing(18)
        secondary.setColumnStretch(0, 1)
        secondary.setColumnStretch(1, 1)
        secondary.addWidget(self._signup_action(), 0, 0)
        secondary.addWidget(self._signup_qr_card(), 0, 1)
        layout.addLayout(secondary)
        layout.addStretch(1)

        footer_frame = QFrame()
        footer_frame.setObjectName("kioskFooter")
        footer = QHBoxLayout(footer_frame)
        footer.setContentsMargins(20, 14, 20, 14)
        footer.setSpacing(12)
        help_text = QLabel("هر روز، قوی‌تر از دیروز  •  برای دریافت کمک به پذیرش مراجعه کنید.")
        help_text.setObjectName("kioskHelpText")
        help_text.setWordWrap(True)
        manager = QPushButton("ورود مدیریت")
        manager.setObjectName("kioskManagerButton")
        manager.setCursor(Qt.CursorShape.PointingHandCursor)
        manager.setAccessibleName("ورود به بخش مدیریت")
        manager.clicked.connect(lambda: self.action_requested.emit("admin"))
        footer.addWidget(help_text, 1)
        footer.insertWidget(0, manager)
        layout.addWidget(footer_frame)

        outer.addWidget(shell)
        outer.addStretch(4)
        scroll.setWidget(content)
        root_layout.addWidget(scroll)

    def _header(self):
        header = QHBoxLayout()
        header.setSpacing(14)

        logo = QLabel()
        logo.setObjectName("kioskBrandLogo")
        logo.setFixedSize(76, 76)
        logo.setAlignment(Qt.AlignmentFlag.AlignCenter)
        logo_path = self.qr_path.parent / "gym-logo-transparent.png" if self.qr_path else None
        pixmap = QPixmap(str(logo_path)) if logo_path else QPixmap()
        if not pixmap.isNull():
            logo.setPixmap(
                pixmap.scaled(
                    68,
                    68,
                    Qt.AspectRatioMode.KeepAspectRatio,
                    Qt.TransformationMode.SmoothTransformation,
                )
            )

        brand_copy = QVBoxLayout()
        brand_copy.setSpacing(1)
        brand = QLabel("LIFE BOX")
        brand.setObjectName("kioskBrandName")
        tagline = QLabel("باشگاه ورزشی لایف‌باکس")
        tagline.setObjectName("kioskBrandTagline")
        brand_copy.addWidget(brand)
        brand_copy.addWidget(tagline)

        self.clock_label = QLabel()
        self.clock_label.setObjectName("kioskClock")
        self.clock_label.setAlignment(Qt.AlignmentFlag.AlignCenter)

        header.addWidget(logo)
        header.addLayout(brand_copy)
        header.addStretch()
        header.addWidget(self.clock_label)
        return header

    def _welcome_block(self):
        container = QWidget()
        container.setObjectName("kioskWelcomeBlock")
        container.setFixedWidth(590)
        block = QVBoxLayout(container)
        block.setContentsMargins(0, 0, 0, 0)
        block.setSpacing(6)
        title = QLabel("خوش آمدید")
        title.setObjectName("kioskTitle")
        subtitle = QLabel("برای ورود به باشگاه، کارت زرد را لمس کنید.")
        subtitle.setObjectName("kioskSubtitle")
        for label in (title, subtitle):
            label.setAlignment(Qt.AlignmentFlag.AlignRight)
            label.setSizePolicy(
                QSizePolicy.Policy.Preferred,
                QSizePolicy.Policy.Preferred,
            )
            label_row = QHBoxLayout()
            label_row.setDirection(QHBoxLayout.Direction.LeftToRight)
            label_row.addStretch(1)
            label_row.addWidget(label)
            block.addLayout(label_row)

        metrics = QHBoxLayout()
        metrics.setDirection(QHBoxLayout.Direction.RightToLeft)
        metrics.setSpacing(12)
        self.inside_value = self._metric(metrics, "افراد حاضر")
        self.today_value = self._metric(metrics, "ورودی امروز")
        metrics.addStretch(1)
        block.addLayout(metrics)
        return container

    @staticmethod
    def _metric(parent_layout, title, object_name="kioskMetric"):
        metric = QFrame()
        metric.setObjectName(object_name)
        metric.setMinimumWidth(168)
        metric_layout = QVBoxLayout(metric)
        metric_layout.setContentsMargins(16, 10, 16, 10)
        metric_layout.setSpacing(0)
        value = QLabel("—")
        value.setObjectName("kioskMetricValue")
        value.setAlignment(Qt.AlignmentFlag.AlignCenter)
        label = QLabel(title)
        label.setObjectName("kioskMetricLabel")
        label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        metric_layout.addWidget(value)
        metric_layout.addWidget(label)
        parent_layout.addWidget(metric)
        return value

    def _primary_action(self):
        card = TouchCard("kioskPrimaryAction")
        card.setMinimumHeight(440)
        card.setAccessibleName("ورود اعضا؛ تشخیص چهره و تخصیص کمد")
        card.clicked.connect(lambda: self.action_requested.emit("attendance"))

        card_layout = QHBoxLayout(card)
        card_layout.setContentsMargins(42, 38, 42, 38)
        card_layout.setSpacing(34)

        icon = QLabel()
        icon.setObjectName("kioskPrimaryIcon")
        icon.setFixedSize(250, 250)
        icon.setAlignment(Qt.AlignmentFlag.AlignCenter)
        icon_path = self.qr_path.parent / "kiosk-face.svg" if self.qr_path else None
        icon_pixmap = QPixmap(str(icon_path)) if icon_path else QPixmap()
        if not icon_pixmap.isNull():
            icon.setPixmap(
                icon_pixmap.scaled(
                    238,
                    238,
                    Qt.AspectRatioMode.KeepAspectRatio,
                    Qt.TransformationMode.SmoothTransformation,
                )
            )

        copy = QVBoxLayout()
        copy.setSpacing(8)
        eyebrow = QLabel("ورود سریع")
        eyebrow.setObjectName("kioskPrimaryEyebrow")
        title = QLabel("ورود اعضا")
        title.setObjectName("kioskPrimaryTitle")
        description = QLabel("کارت را لمس کنید و روبه‌روی دوربین بایستید؛ ورود شما خودکار ثبت می‌شود.")
        description.setObjectName("kioskPrimaryDescription")
        description.setWordWrap(True)
        hint = QLabel("برای شروع لمس کنید")
        hint.setObjectName("kioskPrimaryHint")
        hint.setAlignment(Qt.AlignmentFlag.AlignCenter)
        hint.setFixedWidth(210)

        copy.addWidget(eyebrow)
        copy.addWidget(title)
        copy.addWidget(description)
        copy.addStretch(1)
        copy.addWidget(hint)

        card_layout.addLayout(copy, 1)
        card_layout.addWidget(icon)
        card.make_children_transparent()
        self._add_shadow(card, blur=34, y=12, alpha=36)
        return card

    def _signup_action(self):
        card = TouchCard("kioskSecondaryAction")
        card.setMinimumHeight(520)
        card.setAccessibleName("ثبت‌نام حضوری عضو جدید")
        card.clicked.connect(lambda: self.action_requested.emit("walk_in"))

        card_layout = QVBoxLayout(card)
        card_layout.setContentsMargins(28, 26, 28, 26)
        card_layout.setSpacing(10)
        icon = QLabel()
        icon.setObjectName("kioskSecondaryIcon")
        icon.setFixedSize(90, 90)
        icon.setAlignment(Qt.AlignmentFlag.AlignCenter)
        icon_path = self.qr_path.parent / "kiosk-signup.svg" if self.qr_path else None
        icon_pixmap = QPixmap(str(icon_path)) if icon_path else QPixmap()
        if not icon_pixmap.isNull():
            icon.setPixmap(
                icon_pixmap.scaled(
                    82,
                    82,
                    Qt.AspectRatioMode.KeepAspectRatio,
                    Qt.TransformationMode.SmoothTransformation,
                )
            )
        eyebrow = QLabel("عضو جدید هستید؟")
        eyebrow.setObjectName("kioskSecondaryEyebrow")
        title = QLabel("ثبت‌نام در باشگاه")
        title.setObjectName("kioskSecondaryTitle")
        description = QLabel("پلن خود را انتخاب کنید و مراحل عضویت را همین‌جا انجام دهید.")
        description.setObjectName("kioskSecondaryDescription")
        description.setWordWrap(True)
        hint = QLabel("شروع ثبت‌نام  ←")
        hint.setObjectName("kioskSecondaryHint")
        for label in (eyebrow, title, description, hint):
            label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        hint.setMinimumHeight(58)
        card_layout.addWidget(icon, alignment=Qt.AlignmentFlag.AlignHCenter)
        card_layout.addWidget(eyebrow)
        card_layout.addWidget(title)
        card_layout.addWidget(description)
        card_layout.addStretch()
        card_layout.addWidget(hint)
        card.make_children_transparent()
        self._add_shadow(card, blur=28, y=9, alpha=28)
        return card

    def _signup_qr_card(self):
        card = QFrame()
        card.setObjectName("kioskQrCard")
        card.setMinimumHeight(520)
        card_layout = QVBoxLayout(card)
        card_layout.setContentsMargins(26, 24, 26, 24)
        card_layout.setSpacing(18)

        copy = QVBoxLayout()
        copy.setSpacing(8)
        eyebrow = QLabel("ثبت‌نام با موبایل")
        eyebrow.setObjectName("kioskQrEyebrow")
        title = QLabel("اسکن کنید")
        title.setObjectName("kioskQrTitle")
        hint = QLabel("دوربین موبایل را روبه‌روی QR بگیرید و ثبت‌نام را در گوشی ادامه دهید.")
        hint.setObjectName("kioskQrHint")
        hint.setWordWrap(True)
        network = QLabel("موبایل باید به شبکه باشگاه متصل باشد")
        network.setObjectName("kioskQrNetwork")
        network.setWordWrap(True)
        copy.addWidget(eyebrow)
        copy.addWidget(title)
        copy.addWidget(hint)
        for label in (eyebrow, title, hint, network):
            label.setAlignment(Qt.AlignmentFlag.AlignCenter)

        qr = QLabel()
        qr.setObjectName("kioskQrImage")
        qr.setFixedSize(226, 226)
        qr.setAlignment(Qt.AlignmentFlag.AlignCenter)
        qr.setAccessibleName(f"کد ثبت‌نام آنلاین؛ نشانی {self.signup_url}")
        pixmap = QPixmap(str(self.qr_path)) if self.qr_path else QPixmap()
        if not pixmap.isNull():
            qr.setPixmap(
                pixmap.scaled(
                    212,
                    212,
                    Qt.AspectRatioMode.KeepAspectRatio,
                    Qt.TransformationMode.SmoothTransformation,
                )
            )
        else:
            qr.setText("QR")

        card_layout.addLayout(copy)
        card_layout.addWidget(qr, alignment=Qt.AlignmentFlag.AlignCenter)
        card_layout.addWidget(network)
        self._add_shadow(card, blur=28, y=9, alpha=34)
        return card

    @staticmethod
    def _add_shadow(widget, *, blur, y, alpha):
        shadow = QGraphicsDropShadowEffect(widget)
        shadow.setBlurRadius(blur)
        shadow.setOffset(0, y)
        shadow.setColor(QColor(0, 0, 0, alpha))
        widget.setGraphicsEffect(shadow)

    def _update_clock(self):
        now = datetime.now()
        self.clock_label.setText(
            to_persian_digits(f"{self.WEEKDAYS[now.weekday()]}  •  {now:%H:%M}")
        )

    def showEvent(self, event):
        super().showEvent(event)
        self.refresh()

    def _refresh_if_visible(self):
        if self.isVisible():
            self.refresh()

    def refresh(self):
        if self.busy:
            return
        self.busy = True
        worker = TaskWorker(self.service.load)
        worker.signals.succeeded.connect(self._apply_stats)
        worker.signals.failed.connect(self._show_error)
        worker.signals.finished.connect(self._finish_refresh)
        self.pool.start(worker)

    def _apply_stats(self, stats):
        self.loaded = True
        self.inside_value.setText(self._format_value(stats.inside))
        self.today_value.setText(self._format_value(stats.today_entries))

    @staticmethod
    def _format_value(value):
        if value is None:
            return "—"
        return to_persian_digits(f"{value:,}")

    def _show_error(self, message):
        self.inside_value.setText("—")
        self.today_value.setText("—")

    def _finish_refresh(self):
        self.busy = False
