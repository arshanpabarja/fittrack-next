from PyQt6.QtCore import Qt, QThreadPool, QTimer
from PyQt6.QtGui import QCloseEvent
from PyQt6.QtWidgets import QHBoxLayout, QMainWindow, QStackedWidget, QVBoxLayout, QWidget

from app.domain.models import AppSession
from app.ui.pages.dashboard import DashboardPage
from app.ui.pages.login import ManagerLoginPage
from app.ui.pages.members import MembersPage
from app.ui.pages.pending import PendingApplicationsPage
from app.ui.pages.attendance import AttendancePage
from app.ui.pages.reports import ReportsPage
from app.ui.pages.settings import SettingsPage
from app.ui.pages.coaches import CoachesPage
from app.ui.pages.walk_in import WalkInSignupPage
from app.ui.pages.admin import AdminPanelPage
from app.ui.widgets import Sidebar, TopBar
from app.ui.workers import TaskWorker


class MainWindow(QMainWindow):
    PROTECTED_PAGES = {"members", "pending", "coaches", "reports", "settings", "admin"}

    def __init__(self, settings, services):
        super().__init__()
        self.settings = settings
        self.services = services
        self.session = AppSession()
        self.pool = QThreadPool.globalInstance()
        self.pool.setMaxThreadCount(4)
        self.pending_page = "dashboard"
        self.current_page = "dashboard"
        self.back_page = "dashboard"
        self.pages = {}

        self.setWindowTitle("Life Box | باشگاه ورزشی لایف‌باکس")
        self.resize(1280, 820)
        self.setMinimumSize(1050, 700)
        self.setLayoutDirection(Qt.LayoutDirection.RightToLeft)

        root = QWidget()
        root.setObjectName("appRoot")
        layout = QHBoxLayout(root)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        logo = settings.assets_dir / "icons" / "gym-logo.png"
        self.sidebar = Sidebar(logo)
        self.sidebar.navigation_requested.connect(self.navigate)
        content = QWidget()
        content.setObjectName("contentArea")
        content_layout = QVBoxLayout(content)
        content_layout.setContentsMargins(0, 0, 0, 0)
        content_layout.setSpacing(0)
        self.top_bar = TopBar()
        self.top_bar.back_requested.connect(self._go_back)
        self.stack = QStackedWidget()
        self.stack.setObjectName("pageStack")
        content_layout.addWidget(self.top_bar)
        content_layout.addWidget(self.stack, 1)
        layout.addWidget(self.sidebar)
        layout.addWidget(content, 1)
        self.setCentralWidget(root)

        self._register_pages()
        self.auto_checkout_timer = QTimer(self)
        self.auto_checkout_timer.timeout.connect(self._run_auto_checkout)
        self.auto_checkout_timer.start(60_000)
        QTimer.singleShot(2_000, self._run_auto_checkout)
        self.navigate("dashboard")

    def _register(self, key, widget):
        self.pages[key] = widget
        self.stack.addWidget(widget)

    def _register_pages(self):
        dashboard = DashboardPage(
            self.services.dashboard,
            self.pool,
            self.settings.assets_dir / "icons" / "site-signup-qr.svg",
            f"{self.settings.django_base_url}/signup.html",
        )
        dashboard.action_requested.connect(self.navigate)
        self._register("dashboard", dashboard)
        walk_in = WalkInSignupPage(
            self.services.walk_in,
            self.pool,
            self.settings.project_root / "models",
            self.services.camera_indices,
        )
        walk_in.member_created.connect(self._refresh_face_index)
        self._register("walk_in", walk_in)
        members = MembersPage(self.services.members, self.pool)
        members.face_index_refresh_requested.connect(self._refresh_face_index)
        self._register("members", members)
        pending = PendingApplicationsPage(
            self.services.pending,
            self.services.enrollment,
            self.pool,
            self.settings.project_root / "models",
            self.services.camera_indices,
        )
        pending.membership_activated.connect(self._refresh_face_index)
        self._register("pending", pending)
        self._register("attendance", AttendancePage(
            self.services.attendance,
            self.pool,
            self.settings.project_root / "models",
            self.services.camera_indices,
        ))
        self._register("reports", ReportsPage(self.services.reports, self.pool))
        self._register("coaches", CoachesPage(self.services.coaches, self.pool))
        admin = AdminPanelPage(self.services.reports, self.services.plans, self.pool)
        admin.navigation_requested.connect(self.navigate)
        admin.plans_changed.connect(self._plans_changed)
        self._register("admin", admin)
        self._register("settings", SettingsPage(self.services.preferences, self.pool))
        login = ManagerLoginPage(self.services.auth)
        login.authenticated.connect(self._manager_authenticated)
        login.cancelled.connect(lambda: self.navigate("dashboard"))
        self._register("manager_login", login)

    def navigate(self, key):
        if key not in self.pages:
            return
        if key in self.PROTECTED_PAGES and not self.session.manager_authenticated:
            self.pending_page = key
            login = self.pages["manager_login"]
            login.prepare()
            self.stack.setCurrentWidget(login)
            self.sidebar.select("")
            self.top_bar.set_dashboard(False)
            return
        if key == "coaches" and self.current_page == "admin":
            self.back_page = "admin"
        elif key != self.current_page:
            self.back_page = "dashboard"
        self.stack.setCurrentWidget(self.pages[key])
        self.current_page = key
        self.sidebar.select(key)
        self.top_bar.set_dashboard(key == "dashboard")

    def _go_back(self):
        destination = self.back_page
        self.back_page = "dashboard"
        self.navigate(destination)

    def _run_auto_checkout(self):
        worker = TaskWorker(self.services.attendance.auto_checkout)
        worker.signals.succeeded.connect(self._after_auto_checkout)
        self.pool.start(worker)

    def _after_auto_checkout(self, count):
        if count:
            self.pages["dashboard"].loaded = False
            self.pages["attendance"].refresh_summary()

    def _refresh_face_index(self):
        self.pool.start(TaskWorker(self.services.attendance.refresh_faces))

    def _plans_changed(self):
        self.pages["walk_in"].plans = []

    def _manager_authenticated(self, username):
        self.session.manager_authenticated = True
        self.session.manager_username = username
        self.sidebar.set_manager(username)
        destination = self.pending_page
        self.pending_page = "dashboard"
        self.navigate(destination)

    def closeEvent(self, event: QCloseEvent):
        self.pool.clear()
        super().closeEvent(event)


class Services:
    def __init__(self, *, dashboard, members, auth, pending, enrollment, attendance, reports, preferences, coaches, walk_in, plans, camera_indices):
        self.dashboard = dashboard
        self.members = members
        self.auth = auth
        self.pending = pending
        self.enrollment = enrollment
        self.attendance = attendance
        self.reports = reports
        self.preferences = preferences
        self.coaches = coaches
        self.walk_in = walk_in
        self.plans = plans
        self.camera_indices = camera_indices
