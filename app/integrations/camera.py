import threading
import math
import time

from PyQt6.QtCore import QThread, pyqtSignal
from PyQt6.QtGui import QImage


class CameraWorker(QThread):
    frame_ready = pyqtSignal(QImage)
    face_ready = pyqtSignal(object, bytes)
    status_changed = pyqtSignal(str)
    failed = pyqtSignal(str)

    def __init__(self, models_dir, camera_indices=(0, 1, 2), auto_capture=False, parent=None, capture_delay=0):
        super().__init__(parent)
        self.models_dir = models_dir
        self.camera_indices = camera_indices
        self.auto_capture = auto_capture
        self.capture_requested = threading.Event()
        self.capture_delay = max(0, float(capture_delay))
        self._preview_started = None
        self._last_countdown = None

    def _capture_ready(self, now):
        if self._preview_started is None:
            self._preview_started = now
        remaining = max(0, math.ceil(self.capture_delay - (now - self._preview_started)))
        if remaining != self._last_countdown:
            self._last_countdown = remaining
            self.status_changed.emit(
                f"روبروی دوربین قرار بگیرید؛ اسکن تا {remaining} ثانیه دیگر…"
                if remaining else "آماده اسکن؛ فقط یک نفر روبروی دوربین بایستد."
            )
        return remaining == 0

    def request_capture(self):
        self.capture_requested.set()

    def stop(self):
        self.requestInterruption()
        self.wait(2500)

    def _open_camera(self, cv2):
        for index in self.camera_indices:
            capture = cv2.VideoCapture(index, cv2.CAP_DSHOW)
            if capture.isOpened():
                capture.set(cv2.CAP_PROP_FRAME_WIDTH, 960)
                capture.set(cv2.CAP_PROP_FRAME_HEIGHT, 540)
                return capture
            capture.release()
        return None

    def run(self):
        capture = None
        try:
            import cv2

            detector = cv2.FaceDetectorYN.create(
                str(self.models_dir / "face_detection_yunet_2023mar.onnx"),
                "",
                (320, 320),
            )
            detector.setScoreThreshold(0.75)
            recognizer = cv2.FaceRecognizerSF.create(
                str(self.models_dir / "face_recognition_sface_2021dec.onnx"),
                "",
            )
            self.status_changed.emit("در حال اتصال به دوربین…")
            capture = self._open_camera(cv2)
            if capture is None:
                raise RuntimeError("هیچ دوربین قابل استفاده‌ای پیدا نشد.")
            self.status_changed.emit("صورت را داخل کادر قرار دهید.")
            frame_number = 0
            latest_face = None
            stable_since = None
            while not self.isInterruptionRequested():
                ok, frame = capture.read()
                if not ok:
                    time.sleep(0.04)
                    continue
                frame_number += 1
                capture_ready = self._capture_ready(time.monotonic())
                height, width = frame.shape[:2]
                if frame_number % 3 == 0:
                    detector.setInputSize((width, height))
                    _, faces = detector.detect(frame)
                    latest_face = faces[0] if faces is not None and len(faces) == 1 else None
                    if latest_face is None or not capture_ready:
                        stable_since = None
                    elif stable_since is None:
                        stable_since = time.monotonic()
                    elif self.auto_capture and time.monotonic() - stable_since >= 0.9:
                        self.capture_requested.set()
                        self.auto_capture = False
                        self.status_changed.emit("چهره شناسایی شد؛ در حال پردازش…")
                preview = frame.copy()
                if latest_face is not None:
                    x, y, w, h = [int(value) for value in latest_face[:4]]
                    cv2.rectangle(preview, (x, y), (x + w, y + h), (28, 196, 104), 3)
                if capture_ready and self.capture_requested.is_set():
                    self.capture_requested.clear()
                    if latest_face is None:
                        self.status_changed.emit("چهره پیدا نشد؛ روبه‌روی دوربین بایستید.")
                    else:
                        aligned = recognizer.alignCrop(frame, latest_face)
                        feature = recognizer.feature(aligned).flatten().astype(float).tolist()
                        encoded, image = cv2.imencode(".jpg", aligned, [cv2.IMWRITE_JPEG_QUALITY, 92])
                        if not encoded:
                            raise RuntimeError("ذخیره تصویر چهره انجام نشد.")
                        self.face_ready.emit(feature, image.tobytes())
                rgb = cv2.cvtColor(preview, cv2.COLOR_BGR2RGB)
                image = QImage(
                    rgb.data,
                    width,
                    height,
                    rgb.strides[0],
                    QImage.Format.Format_RGB888,
                ).copy()
                self.frame_ready.emit(image)
                self.msleep(20)
        except Exception as exc:
            self.failed.emit(str(exc) or "دوربین آماده نشد.")
        finally:
            if capture is not None:
                capture.release()
