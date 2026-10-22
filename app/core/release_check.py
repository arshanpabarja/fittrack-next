"""Licensed, hardware-free smoke check for the compiled desktop package."""

import os
from pathlib import Path
import traceback

from PyQt6.QtCore import QThreadPool, QTimer

from app.integrations.django_api import DjangoApiClient, _ca_bundle_path
from app.integrations.pos import _load_pcpos
from app.ui.workers import TaskWorker


def run_release_check(app, root):
    diagnostic = os.getenv("FITTRACK_RELEASE_CHECK_DIAGNOSTIC", "").strip()

    def fail(code, exc=None):
        if diagnostic:
            details = [f"code={code}", f"root={root}"]
            try:
                bundle = Path(_ca_bundle_path())
                details.extend((f"ca={bundle}", f"ca_exists={bundle.is_file()}"))
            except Exception:
                details.append("ca_lookup=" + traceback.format_exc())
            if exc is not None:
                details.append("exception=" + repr(exc))
                details.append(traceback.format_exc())
            Path(diagnostic).write_text("\n".join(details), encoding="utf-8")
        return code

    required = (
        "Vazirmatn-Bold.ttf", "app/ui/theme.qss", "assets/welcome.wav",
        "models/face_detection_yunet_2023mar.onnx",
        "models/face_recognition_sface_2021dec.onnx", "Library/pec.pcpos.dll",
        "certifi/cacert.pem",
    )
    if not all((root / name).is_file() for name in required):
        return fail(3)
    # Load the real .NET assembly but never instantiate a terminal, send a
    # transaction, open a camera, connect to the API, or read club data.
    try:
        _load_pcpos()
    except Exception as exc:
        return fail(4, exc)
    # Construct the real HTTPS client without sending a request. This catches
    # missing or misplaced CA bundles in the standalone distribution.
    try:
        api = DjangoApiClient("https://example.invalid", "release-check")
        if not api.ssl_context.check_hostname:
            return 8
    except Exception as exc:
        return fail(8, exc)
    received = []
    worker = TaskWorker(lambda: {"worker": "ok"})
    worker.signals.succeeded.connect(received.append)
    worker.signals.failed.connect(lambda error: app.exit(5))
    worker.signals.finished.connect(lambda: app.exit(0 if received == [{"worker": "ok"}] else 6))
    timer = QTimer()
    timer.setSingleShot(True)
    timer.timeout.connect(lambda: app.exit(7))
    timer.start(10_000)
    pool = QThreadPool()
    QTimer.singleShot(0, lambda: pool.start(worker))
    result = app.exec()
    pool.waitForDone(2000)
    return result
