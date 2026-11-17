import logging
import os
import sys
from pathlib import Path

from PyQt6.QtGui import QFont, QFontDatabase
from PyQt6.QtCore import QTimer
from PyQt6.QtWidgets import QApplication, QMessageBox

from app.core.config import load_settings
from app.core.logging import configure_logging
from app.data.manager import ManagerRepository
from app.data.members import MembersRepository
from app.data.memberships import MembershipRepository
from app.data.enrollments import EnrollmentRepository
from app.data.attendance import AttendanceRepository
from app.data.preferences import PreferencesRepository
from app.data.audit import AuditRepository
from app.data.telemetry import TelemetryRepository
from app.integrations.django_api import DjangoApiClient
from app.integrations.pos import create_pos_terminal
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
from app.services.plans import PlansService
from app.services.cloud_sync import CloudSyncService
from app.services.audit import AuditService
from app.services.telemetry import TelemetryService
from app.services.updater import UpdateService
from app.ui.main_window import MainWindow, Services
from app.ui.activation import ensure_activation


def _exception_hook(exc_type, exc_value, exc_traceback):
    logging.getLogger(__name__).critical(
        "Unhandled application error",
        exc_info=(exc_type, exc_value, exc_traceback),
    )
    sys.__excepthook__(exc_type, exc_value, exc_traceback)


def build_services(settings, telemetry_repository=None):
    members_repository = MembersRepository(settings.members_database)
    audit_service = AuditService(AuditRepository(settings.state_database))
    preferences_service = PreferencesService(
        PreferencesRepository(settings.state_database),
        audit_service,
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
    pos_terminal = create_pos_terminal(runtime)
    plans_service = PlansService(api, settings.data_dir / "plans.json", audit_service)
    cloud_sync = None
    telemetry = None
    updater = None
    if os.getenv('FITTRACK_CLOUD_SYNC') == '1':
        cloud_sync = CloudSyncService(api, settings.members_database, settings.state_database,
                                      plans_service, os.getenv('FITTRACK_SYNC_SOURCE', ''), workflows)
        telemetry = TelemetryService(
            api,
            telemetry_repository or TelemetryRepository(settings.state_database),
            os.getenv('FITTRACK_SYNC_SOURCE', ''),
            settings.state_database,
            cloud_sync.queue_path,
        )
        updater = UpdateService(
            api,
            telemetry,
            settings.project_root,
            settings.log_dir.parent,
        )
    member_service = MemberService(
        members_repository,
        membership_repository,
        pos_terminal,
        api,
        audit_service,
    )
    member_service.recover_incomplete_renewals()
    return Services(
        dashboard=DashboardService(
            settings.members_database,
            settings.attendance_database,
            settings.single_session_database,
            current_attendance=attendance_repository,
        ),
        members=member_service,
        auth=AuthService(ManagerRepository(settings.manager_database), audit_service),
        pending=PendingApplicationsService(api),
        enrollment=EnrollmentService(
            api,
            workflows,
            members_repository,
            pos_terminal,
            cloud_sync=cloud_sync,
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
        coaches=CoachesService(api, audit_service),
        walk_in=WalkInSignupService(
            settings.data_dir / "plans.json",
            members_repository,
            pos_terminal,
        ),
        plans=plans_service,
        audit=audit_service,
        camera_indices=camera_indices,
        cloud_sync=cloud_sync,
        telemetry=telemetry,
        updater=updater,
    )


def run():
    sys.excepthook = _exception_hook
    app = QApplication(sys.argv)
    app.setApplicationName("Life Box")
    app.setOrganizationName("LifeBox Gym")

    package_root = Path(__file__).resolve().parent.parent
    font_path = package_root / "Vazirmatn-Bold.ttf"
    if font_path.exists():
        font_id = QFontDatabase.addApplicationFont(str(font_path))
        families = QFontDatabase.applicationFontFamilies(font_id)
        if families:
            app.setFont(QFont(families[0], 10))

    theme_path = Path(__file__).resolve().parent / "ui" / "theme.qss"
    app.setStyleSheet(theme_path.read_text(encoding="utf-8"))
    if not ensure_activation(package_root):
        return 1
    if "--check-desktop-release" in sys.argv:
        from app.core.release_check import run_release_check
        return run_release_check(app, package_root)
    settings = load_settings()
    telemetry_repository = TelemetryRepository(settings.state_database)
    configure_logging(settings.log_dir, telemetry_repository)
    if not settings.data_dir.is_dir():
        QMessageBox.critical(None, "لایف‌باکس", f"پوشهٔ دیتابیس باشگاه پیدا نشد:\n{settings.data_dir}")
        return 1
    window = MainWindow(settings, build_services(settings, telemetry_repository))
    if os.getenv("FITTRACK_WINDOWED", "").strip().lower() in {"1", "true", "yes"}:
        window.show()
    else:
        window.showFullScreen()
    def write_update_marker():
        try:
            marker_index = sys.argv.index("--update-marker") + 1
            marker = Path(sys.argv[marker_index])
            marker.parent.mkdir(parents=True, exist_ok=True)
            temporary = marker.with_suffix(".tmp")
            temporary.write_text("ready", encoding="utf-8")
            os.replace(temporary, marker)
        except (ValueError, IndexError, OSError):
            logging.getLogger(__name__).exception("Could not write post-update health marker")
    if "--update-marker" in sys.argv:
        # Let the Qt event loop and initial widgets settle before declaring the
        # new release healthy to the external updater.
        QTimer.singleShot(1_000, write_update_marker)
    return app.exec()
