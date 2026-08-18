import logging
import sys
from pathlib import Path

from PyQt6.QtGui import QFont, QFontDatabase
from PyQt6.QtWidgets import QApplication

from app.core.config import load_settings
from app.core.logging import configure_logging
from app.data.manager import ManagerRepository
from app.data.members import MembersRepository
from app.data.memberships import MembershipRepository
from app.data.enrollments import EnrollmentRepository
from app.data.attendance import AttendanceRepository
from app.data.preferences import PreferencesRepository
from app.integrations.django_api import DjangoApiClient
from app.integrations.pos import FakePosTerminal
from app.integrations.access_control import SimulatedAccessController
from app.services.auth import AuthService
from app.services.dashboard import DashboardService
from app.services.members import MemberService
from app.services.enrollment import EnrollmentService, PendingApplicationsService
from app.services.attendance import AttendanceService
from app.services.face_index import FaceIndex
from app.services.reports import ReportsService
from app.services.preferences import PreferencesService
from app.services.coaches import CoachesService
from app.services.walk_in import WalkInSignupService
from app.ui.main_window import MainWindow, Services


def _exception_hook(exc_type, exc_value, exc_traceback):
    logging.getLogger(__name__).critical(
        "Unhandled application error",
        exc_info=(exc_type, exc_value, exc_traceback),
    )
    sys.__excepthook__(exc_type, exc_value, exc_traceback)


def build_services(settings):
    members_repository = MembersRepository(settings.members_database)
    preferences_service = PreferencesService(
        PreferencesRepository(settings.state_database)
    )
    runtime = preferences_service.load()
    camera_indices = tuple(
        int(item.strip()) for item in runtime["camera_indices"].split(",")
    )
    api = DjangoApiClient(
        runtime["api_url"],
        settings.desktop_api_token,
    )
    workflows = EnrollmentRepository(settings.state_database)
    attendance_repository = AttendanceRepository(
        settings.state_database,
        locker_count=int(runtime["locker_count"]),
    )
    membership_repository = MembershipRepository(settings.state_database)
    if runtime["pos_mode"] != "fake":
        raise RuntimeError("در این نسخه فقط FITTRACK_POS_MODE=fake فعال است.")
    return Services(
        dashboard=DashboardService(
            settings.members_database,
            settings.attendance_database,
            settings.single_session_database,
            current_attendance=attendance_repository,
        ),
        members=MemberService(
            members_repository,
            membership_repository,
            FakePosTerminal(),
            api,
        ),
        auth=AuthService(ManagerRepository(settings.manager_database)),
        pending=PendingApplicationsService(api),
        enrollment=EnrollmentService(
            api,
            workflows,
            members_repository,
            FakePosTerminal(),
        ),
        attendance=AttendanceService(
            FaceIndex(members_repository, threshold=float(runtime["face_threshold"])),
            attendance_repository,
            members_repository,
            SimulatedAccessController(),
            membership_repository,
        ),
        reports=ReportsService(attendance_repository),
        preferences=preferences_service,
        coaches=CoachesService(api),
        walk_in=WalkInSignupService(
            settings.data_dir / "plans.json",
            members_repository,
            FakePosTerminal(),
        ),
        camera_indices=camera_indices,
    )


def run():
    settings = load_settings()
    configure_logging(settings.log_dir)
    sys.excepthook = _exception_hook
    app = QApplication(sys.argv)
    app.setApplicationName("FitTrack Next")
    app.setOrganizationName("LifeBox Gym")

    font_path = settings.project_root / "Vazirmatn-Bold.ttf"
    if font_path.exists():
        font_id = QFontDatabase.addApplicationFont(str(font_path))
        families = QFontDatabase.applicationFontFamilies(font_id)
        if families:
            app.setFont(QFont(families[0], 10))

    theme_path = Path(__file__).resolve().parent / "ui" / "theme.qss"
    app.setStyleSheet(theme_path.read_text(encoding="utf-8"))
    window = MainWindow(settings, build_services(settings))
    window.show()
    return app.exec()
