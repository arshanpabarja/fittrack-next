from datetime import datetime, timedelta

from PyQt6.QtCore import Qt, QThreadPool, QTimer, pyqtSignal
from PyQt6.QtWidgets import (
    QDialog,
    QFrame,
    QFormLayout,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QMessageBox,
    QPushButton,
    QScrollArea,
    QVBoxLayout,
    QWidget,
)

from app.ui.face_capture import FaceCaptureDialog
from app.ui.pages.members import RenewalDialog
from app.ui.widgets import TouchCard
from app.ui.workers import TaskWorker
from app.domain.dates import normalize_membership_datetime


class MemberInfoDialog(QDialog):
    """Read-only face lookup; no attendance or membership mutation."""

    def __init__(self, member, parent=None):
        super().__init__(parent)
        self.setWindowTitle("مشخصات عضو")
        self.setLayoutDirection(Qt.LayoutDirection.RightToLeft)
        self.resize(660, 640)
        layout = QVBoxLayout(self)
        title = QLabel(member.full_name)
        title.setTextFormat(Qt.TextFormat.PlainText)
        title.setObjectName("dialogTitle")
        layout.addWidget(title)
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.Shape.NoFrame)
        content = QWidget()
        form = QFormLayout(content)
        form.setSpacing(14)
        remaining = member.remaining_sessions
        fields = (
            ("شناسه عضویت", member.id), ("نام", member.first_name),
            ("نام خانوادگی", member.last_name), ("نام پدر", member.father_name),
            ("موبایل", member.mobile), ("کد ملی", member.national_id),
            ("شماره شناسنامه", member.certificate_no), ("سن", member.age),
            ("جنسیت", member.gender), ("آدرس", member.address),
            ("پلن", member.plan), ("تاریخ ثبت‌نام", normalize_membership_datetime(member.signup_time)),
            ("کل جلسات پلن", member.session_allowance),
            ("جلسات استفاده‌شده", member.used_sessions),
            ("جلسات باقی‌مانده", remaining),
            ("پرداخت ثبت‌شده", f"{member.payment:,} تومان"),
            ("بدهی", f"{member.debt:,} تومان"),
        )
        for label, value in fields:
            field = QLabel("نامشخص" if value is None or value == "" else str(value))
            field.setTextFormat(Qt.TextFormat.PlainText)
            field.setWordWrap(True)
            field.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
            form.addRow(label, field)
        scroll.setWidget(content)
        layout.addWidget(scroll, 1)
        close = QPushButton("بستن مشخصات")
        close.clicked.connect(self.accept)
        layout.addWidget(close)


class CheckInSuccessDialog(QDialog):
    def __init__(self, result, parent=None):
        super().__init__(parent)
        self.result = result
        self.wants_renewal = False
        self.setWindowTitle("ورود موفق")
        self.setModal(True)
        self.setFixedSize(660, 520)
        self.setLayoutDirection(Qt.LayoutDirection.RightToLeft)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(34, 30, 34, 28)
        layout.setSpacing(14)

        icon = QLabel("✓")
        icon.setObjectName("checkInSuccessIcon")
        icon.setFixedSize(72, 72)
        icon.setAlignment(Qt.AlignmentFlag.AlignCenter)
        title = QLabel("ورود با موفقیت ثبت شد")
        title.setObjectName("checkInSuccessTitle")
        title.setAlignment(Qt.AlignmentFlag.AlignCenter)
        member = QLabel(result.member.full_name)
        member.setObjectName("checkInMemberName")
        member.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(icon, alignment=Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(title)
        layout.addWidget(member)

        try:
            checkout = datetime.strptime(result.occurred_at, "%Y-%m-%d %H:%M:%S") + timedelta(minutes=60)
            checkout_text = checkout.strftime("%H:%M")
        except (TypeError, ValueError):
            checkout_text = "۶۰ دقیقه دیگر"
        remaining = result.member.remaining_sessions
        remaining_text = "نامشخص" if remaining is None else str(remaining)
        signup_text = result.member.signup_time or "ثبت نشده"

        info = QGridLayout()
        info.setSpacing(12)
        fields = (
            ("تاریخ شروع عضویت", signup_text),
            ("خروج خودکار", checkout_text),
            ("جلسات باقی‌مانده", remaining_text),
            ("شماره کمد", str(result.locker_id or "—")),
        )
        for index, (label, value) in enumerate(fields):
            box = QFrame()
            box.setObjectName("checkInInfoBox")
            box_layout = QVBoxLayout(box)
            box_layout.setContentsMargins(16, 13, 16, 13)
            key = QLabel(label)
            key.setObjectName("checkInInfoLabel")
            key.setAlignment(Qt.AlignmentFlag.AlignCenter)
            content = QLabel(value)
            content.setObjectName("checkInInfoValue")
            content.setAlignment(Qt.AlignmentFlag.AlignCenter)
            content.setWordWrap(True)
            box_layout.addWidget(key)
            box_layout.addWidget(content)
            info.addWidget(box, index // 2, index % 2)
        layout.addLayout(info)

        if remaining is not None and remaining <= 0:
            renewal = QLabel(
                "جلسات عضویت شما تمام شده است؛ می‌توانید همین حالا پلن را انتخاب و عضویت را تمدید کنید."
            )
            renewal.setObjectName("checkInRenewalWarning")
            renewal.setAlignment(Qt.AlignmentFlag.AlignCenter)
            renewal.setWordWrap(True)
            layout.addWidget(renewal)
        actions = QHBoxLayout()
        close = QPushButton("متوجه شدم")
        close.setMinimumHeight(56)
        close.clicked.connect(self.accept)
        actions.addWidget(close)
        if result.member.renewal_required:
            renew = QPushButton("تمدید عضویت")
            renew.setObjectName("renewButton")
            renew.setMinimumHeight(56)
            renew.clicked.connect(self._choose_renewal)
            actions.addWidget(renew)
        layout.addLayout(actions)
        QTimer.singleShot(15_000, self.accept)

    def _choose_renewal(self):
        self.wants_renewal = True
        self.accept()


class AttendancePage(QWidget):
    completed = pyqtSignal()

    def __init__(
        self,
        service,
        pool: QThreadPool,
        models_dir,
        camera_indices,
        member_service=None,
        plan_provider=None,
    ):
        super().__init__()
        self.service = service
        self.pool = pool
        self.models_dir = models_dir
        self.camera_indices = camera_indices
        self.member_service = member_service
        self.plan_provider = plan_provider
        self.busy = False
        self._build()

    def _build(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(32, 28, 32, 28)
        layout.setSpacing(18)
        header = QHBoxLayout()
        title_box = QVBoxLayout()
        title = QLabel("ورود اعضا")
        title.setObjectName("attendanceTitle")
        subtitle = QLabel("تشخیص خودکار چهره و تخصیص کمد؛ خروج پس از ۶۰ دقیقه خودکار ثبت می‌شود.")
        subtitle.setObjectName("attendanceSubtitle")
        subtitle.setWordWrap(True)
        title_box.addWidget(title)
        title_box.addWidget(subtitle)
        refresh = QPushButton("بازخوانی چهره‌ها")
        refresh.setObjectName("secondaryButton")
        refresh.clicked.connect(self.refresh_faces)
        header.addLayout(title_box)
        header.addStretch()
        header.addWidget(refresh)
        layout.addLayout(header)

        self.summary = QLabel("در حال دریافت وضعیت کمدها…")
        self.summary.setObjectName("attendanceSummary")
        layout.addWidget(self.summary)

        actions_container = QWidget()
        actions = QVBoxLayout(actions_container)
        actions.setContentsMargins(0, 0, 0, 0)
        actions.setSpacing(18)
        check_in = self._action_card(
            "ورود عضو",
            "کارت را لمس کنید و روبه‌روی دوربین بایستید؛ نیازی به زدن دکمه ثبت چهره نیست.",
            True,
            self.capture,
        )
        actions.addWidget(check_in)
        actions.addWidget(self._action_card(
            "مشاهده مشخصات عضو",
            "این کارت را لمس کنید و چهره را اسکن کنید تا اطلاعات کامل عضویت نمایش داده شود.",
            False, self.capture_info,
        ))
        actions.addStretch()
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.Shape.NoFrame)
        scroll.setWidget(actions_container)
        layout.addWidget(scroll, 1)

    def _action_card(self, title, description, primary, callback):
        card = TouchCard("primaryAction" if primary else "actionCard")
        card.setFixedHeight(300)
        card.setStyleSheet("QFrame#primaryAction, QFrame#actionCard { min-height: 300px; max-height: 300px; }")
        card.clicked.connect(callback)
        layout = QVBoxLayout(card)
        layout.setContentsMargins(24, 22, 24, 22)
        heading = QLabel(title)
        heading.setObjectName("attendanceEntryTitle" if primary else "attendanceInfoTitle")
        heading.setWordWrap(True)
        detail = QLabel(description)
        detail.setObjectName("attendanceEntryDescription" if primary else "attendanceInfoDescription")
        detail.setWordWrap(True)
        hint = QLabel("برای ورود این کارت را لمس کنید" if primary else "مشاهده اطلاعات، بدون ثبت ورود یا کسر جلسه")
        hint.setWordWrap(True)
        hint.setObjectName("actionLink")
        layout.addWidget(heading)
        layout.addWidget(detail)
        layout.addStretch()
        layout.addWidget(hint)
        card.make_children_transparent()
        return card

    def showEvent(self, event):
        super().showEvent(event)
        self.refresh_summary()

    def refresh_faces(self):
        self._run(
            self.service.refresh_faces,
            lambda count: QMessageBox.information(
                self, "بازخوانی انجام شد", f"اطلاعات چهره {count} عضو بازخوانی شد."
            ),
        )

    def refresh_summary(self):
        worker = TaskWorker(self.service.summary)
        worker.signals.succeeded.connect(
            lambda value: self.summary.setText(
                f"افراد حاضر: {value['inside']:,}     |     کمد خالی: {value['free_lockers']:,}"
            )
        )
        worker.signals.failed.connect(lambda message: self.summary.setText(message))
        self.pool.start(worker)

    def capture(self):
        if self.busy:
            return
        dialog = FaceCaptureDialog(
            self.models_dir,
            self.camera_indices,
            self,
            auto_capture=True,
        )
        dialog.captured.connect(
            lambda embedding, image: self._process(embedding)
        )
        dialog.exec()

    def _process(self, embedding):
        self._run(self.service.check_in, self._show_result, embedding)

    def capture_info(self):
        if self.busy:
            return
        dialog = FaceCaptureDialog(self.models_dir, self.camera_indices, self, auto_capture=True)
        dialog.captured.connect(lambda embedding, image: self._run(
            self.service.lookup_member, self._show_member_info, embedding,
        ))
        dialog.exec()

    def _show_member_info(self, member):
        MemberInfoDialog(member, self).exec()

    def _run(self, operation, success, *args):
        if self.busy:
            return
        self.busy = True
        worker = TaskWorker(operation, *args)
        worker.signals.succeeded.connect(success)
        worker.signals.failed.connect(self._failed)
        worker.signals.finished.connect(self._finished)
        self.pool.start(worker)

    def _show_result(self, result):
        self.refresh_summary()
        dialog = CheckInSuccessDialog(result, self)
        dialog.exec()
        if dialog.wants_renewal:
            self._load_renewal(result.member.id)
        else:
            self.completed.emit()

    def _load_renewal(self, member_id):
        if self.member_service is None or self.plan_provider is None:
            QMessageBox.warning(
                self,
                "تمدید آماده نیست",
                "سرویس تمدید عضویت در این دستگاه پیکربندی نشده است.",
            )
            self.completed.emit()
            return
        worker = TaskWorker(self._renewal_context, member_id)
        worker.signals.succeeded.connect(self._open_renewal)
        worker.signals.failed.connect(self._renewal_load_failed)
        self.pool.start(worker)

    def _renewal_context(self, member_id):
        return self.member_service.get_member(member_id), self.plan_provider.list_plans()

    def _open_renewal(self, context):
        member, plans = context
        dialog = RenewalDialog(member, self, plans=plans)
        dialog.submit_requested.connect(
            lambda values: self._renew_member(dialog, member.id, values)
        )
        dialog.exec()
        self.completed.emit()

    def _renew_member(self, dialog, member_id, values):
        worker = TaskWorker(
            self.member_service.renew_member,
            member_id,
            values["plan"],
            values["amount"],
        )
        worker.signals.succeeded.connect(
            lambda result: self._renewal_succeeded(dialog, result)
        )
        worker.signals.failed.connect(dialog.operation_failed)
        self.pool.start(worker)

    def _renewal_succeeded(self, dialog, result):
        dialog.accept()
        QMessageBox.information(
            self,
            "عضویت تمدید شد",
            f"عضویت {result.member.full_name} با موفقیت تمدید شد.\n"
            f"جلسات باقی‌مانده: {result.member.remaining_sessions}\n"
            f"شروع پلن: {result.membership_started_at}\n"
            f"رسید پرداخت: {result.payment_reference}",
        )

    def _renewal_load_failed(self, message):
        QMessageBox.warning(self, "تمدید آماده نشد", message)
        self.completed.emit()

    def _failed(self, message):
        QMessageBox.warning(self, "عملیات انجام نشد", message)

    def _finished(self):
        self.busy = False
