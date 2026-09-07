from datetime import datetime

from PyQt6.QtCore import Qt, QTimer, pyqtSignal
from PyQt6.QtGui import QPixmap
from PyQt6.QtWidgets import (
    QFrame,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QVBoxLayout,
    QWidget,
)


PERSIAN_DIGITS = str.maketrans("0123456789", "۰۱۲۳۴۵۶۷۸۹")


def to_persian_digits(value):
    return str(value).translate(PERSIAN_DIGITS)


class Sidebar(QFrame):
    navigation_requested = pyqtSignal(str)
    logout_requested = pyqtSignal()

    ITEMS = (
        ("dashboard", "صفحه عمومی", "⌂"),
        ("admin", "نمای کلی مدیریت", "▦"),
        ("pending", "پذیرش سایت", "↻"),
        ("walk_in", "ثبت‌نام حضوری", "+"),
        ("members", "اعضا", "◉"),
        ("coaches", "مربی‌ها", "◇"),
        ("attendance", "ورود اعضا", "→"),
        ("reports", "گزارش‌ها", "▥"),
        ("settings", "تنظیمات", "⚙"),
    )

    def __init__(self, logo_path):
        super().__init__()
        self.setObjectName("sidebar")
        self.setFixedWidth(250)
        self.buttons = {}
        layout = QVBoxLayout(self)
        layout.setContentsMargins(20, 24, 20, 20)
        layout.setSpacing(7)

        brand = QHBoxLayout()
        brand.setDirection(QHBoxLayout.Direction.RightToLeft)
        logo = QLabel()
        logo.setObjectName("brandLogo")
        logo.setFixedSize(50, 50)
        logo.setAlignment(Qt.AlignmentFlag.AlignCenter)
        pixmap = QPixmap(str(logo_path))
        if not pixmap.isNull():
            logo.setPixmap(
                pixmap.scaled(
                    46,
                    46,
                    Qt.AspectRatioMode.KeepAspectRatio,
                    Qt.TransformationMode.SmoothTransformation,
                )
            )
        else:
            logo.setText("L")
        names = QVBoxLayout()
        names.setSpacing(0)
        title = QLabel("LIFE BOX")
        title.setObjectName("brandTitle")
        subtitle = QLabel("باشگاه ورزشی لایف‌باکس")
        subtitle.setObjectName("brandSubtitle")
        names.addWidget(title)
        names.addWidget(subtitle)
        brand.addWidget(logo)
        brand.addLayout(names, 1)
        layout.addLayout(brand)
        layout.addSpacing(24)

        section = QLabel("بخش مدیریت")
        section.setObjectName("sidebarSection")
        layout.addWidget(section)
        for key, title, symbol in self.ITEMS:
            button = QPushButton(f"{symbol}   {title}")
            button.setObjectName("navButton")
            button.setCheckable(True)
            button.setCursor(Qt.CursorShape.PointingHandCursor)
            button.clicked.connect(
                lambda checked=False, page=key: self.navigation_requested.emit(page)
            )
            self.buttons[key] = button
            layout.addWidget(button)
        layout.addStretch()

        self.session_label = QLabel("")
        self.session_label.setObjectName("sessionLabel")
        self.session_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.session_label.hide()
        layout.addWidget(self.session_label)

        self.logout_button = QPushButton("خروج از مدیریت")
        self.logout_button.setObjectName("logoutButton")
        self.logout_button.setCursor(Qt.CursorShape.PointingHandCursor)
        self.logout_button.clicked.connect(self.logout_requested.emit)
        self.logout_button.hide()
        layout.addWidget(self.logout_button)

    def select(self, key):
        for page, button in self.buttons.items():
            button.setChecked(page == key)

    def set_manager(self, username=None):
        if username:
            self.session_label.setText(f"مدیر فعال: {username}")
            self.session_label.show()
            self.logout_button.show()
            return
        self.session_label.clear()
        self.session_label.hide()
        self.logout_button.hide()


class TopBar(QFrame):
    back_requested = pyqtSignal()

    WEEKDAYS = (
        "دوشنبه", "سه‌شنبه", "چهارشنبه", "پنج‌شنبه",
        "جمعه", "شنبه", "یکشنبه",
    )

    def __init__(self):
        super().__init__()
        self.setObjectName("topBar")
        layout = QHBoxLayout(self)
        layout.setContentsMargins(28, 12, 28, 12)
        self.date_label = QLabel()
        self.date_label.setObjectName("topDate")
        self.back_button = QPushButton("بازگشت  ←")
        self.back_button.setObjectName("backButton")
        self.back_button.setCursor(Qt.CursorShape.PointingHandCursor)
        self.back_button.clicked.connect(self.back_requested)
        layout.addWidget(self.date_label)
        layout.addStretch()
        layout.addWidget(self.back_button)
        self.timer = QTimer(self)
        self.timer.timeout.connect(self.update_date)
        self.timer.start(60_000)
        self.update_date()

    def update_date(self):
        now = datetime.now()
        self.date_label.setText(
            to_persian_digits(
                f"{self.WEEKDAYS[now.weekday()]}  •  {now:%Y/%m/%d}  •  {now:%H:%M}"
            )
        )

    def set_dashboard(self, is_dashboard):
        self.back_button.setVisible(not is_dashboard)


class TouchCard(QFrame):
    clicked = pyqtSignal()

    def __init__(self, object_name="actionCard"):
        super().__init__()
        self.setObjectName(object_name)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)

    def make_children_transparent(self):
        for child in self.findChildren(QWidget):
            child.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents, True)

    def mouseReleaseEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton and self.rect().contains(event.position().toPoint()):
            self.clicked.emit()
        super().mouseReleaseEvent(event)

    def keyPressEvent(self, event):
        if event.key() in (Qt.Key.Key_Return, Qt.Key.Key_Enter, Qt.Key.Key_Space):
            self.clicked.emit()
            event.accept()
            return
        super().keyPressEvent(event)


class StatCard(QFrame):
    def __init__(self, title, symbol):
        super().__init__()
        self.setObjectName("statCard")
        layout = QHBoxLayout(self)
        layout.setDirection(QHBoxLayout.Direction.RightToLeft)
        layout.setContentsMargins(18, 16, 18, 16)
        icon = QLabel(symbol)
        icon.setObjectName("statIcon")
        icon.setFixedSize(44, 44)
        icon.setAlignment(Qt.AlignmentFlag.AlignCenter)
        copy = QVBoxLayout()
        copy.setSpacing(0)
        label = QLabel(title)
        label.setObjectName("statLabel")
        self.value = QLabel("—")
        self.value.setObjectName("statValue")
        copy.addWidget(label)
        copy.addWidget(self.value)
        layout.addWidget(icon)
        layout.addLayout(copy, 1)

    def set_value(self, value):
        self.value.setText("—" if value is None else f"{value:,}")
