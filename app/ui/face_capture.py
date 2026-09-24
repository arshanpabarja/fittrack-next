from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtGui import QPixmap
from PyQt6.QtWidgets import (
    QDialog,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QVBoxLayout,
)

from app.integrations.camera import CameraWorker


class FaceCaptureDialog(QDialog):
    captured = pyqtSignal(object, bytes)

    def __init__(self, models_dir, camera_indices=(0, 1, 2), parent=None, auto_capture=False, capture_delay=0):
        super().__init__(parent)
        self.setWindowTitle("ثبت چهره عضو")
        self.resize(760, 620)
        self.setModal(True)
        self.auto_capture = auto_capture
        self.worker = CameraWorker(
            models_dir,
            camera_indices=camera_indices,
            auto_capture=auto_capture,
            capture_delay=capture_delay,
            parent=self,
        )
        self.worker.frame_ready.connect(self._show_frame)
        self.worker.face_ready.connect(self._captured)
        self.worker.status_changed.connect(self._set_status)
        self.worker.failed.connect(self._failed)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(28, 24, 28, 24)
        layout.setSpacing(14)
        title = QLabel("شناسایی خودکار چهره" if auto_capture else "ثبت چهره")
        title.setObjectName("dialogTitle")
        subtitle = QLabel(
            "روبروی دوربین بایستید؛ چهره به‌صورت خودکار اسکن می‌شود."
            if auto_capture
            else "نور صورت کافی باشد و فقط یک نفر مقابل دوربین قرار بگیرد."
        )
        subtitle.setObjectName("pageSubtitle")
        self.preview = QLabel("در حال آماده‌سازی دوربین…")
        self.preview.setObjectName("cameraPreview")
        self.preview.setMinimumSize(640, 420)
        self.preview.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.preview.setScaledContents(False)
        self.status = QLabel("")
        self.status.setObjectName("cameraStatus")
        self.status.setAlignment(Qt.AlignmentFlag.AlignCenter)
        buttons = QHBoxLayout()
        self.capture_button = QPushButton("ثبت این چهره")
        self.capture_button.clicked.connect(self.worker.request_capture)
        cancel = QPushButton("انصراف")
        cancel.setObjectName("secondaryButton")
        cancel.clicked.connect(self.reject)
        buttons.addWidget(self.capture_button)
        buttons.addWidget(cancel)
        layout.addWidget(title)
        layout.addWidget(subtitle)
        layout.addWidget(self.preview, 1)
        layout.addWidget(self.status)
        layout.addLayout(buttons)
        self.capture_button.setVisible(not auto_capture)

    def showEvent(self, event):
        super().showEvent(event)
        if not self.worker.isRunning():
            self.worker.start()

    def closeEvent(self, event):
        self.worker.stop()
        super().closeEvent(event)

    def reject(self):
        self.worker.stop()
        super().reject()

    def _show_frame(self, image):
        pixmap = QPixmap.fromImage(image)
        self.preview.setPixmap(
            pixmap.scaled(
                self.preview.size(),
                Qt.AspectRatioMode.KeepAspectRatio,
                Qt.TransformationMode.SmoothTransformation,
            )
        )

    def _set_status(self, message):
        self.status.setText(message)

    def _failed(self, message):
        self.status.setText(message)
        self.status.setObjectName("formError")
        self.status.style().unpolish(self.status)
        self.status.style().polish(self.status)
        self.capture_button.setEnabled(False)

    def _captured(self, embedding, image):
        self.captured.emit(embedding, image)
        self.worker.stop()
        self.accept()
