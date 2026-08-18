import logging
import traceback

from PyQt6.QtCore import QObject, QRunnable, pyqtSignal, pyqtSlot


class WorkerSignals(QObject):
    succeeded = pyqtSignal(object)
    failed = pyqtSignal(str)
    finished = pyqtSignal()


class TaskWorker(QRunnable):
    def __init__(self, function, *args, **kwargs):
        super().__init__()
        self.function = function
        self.args = args
        self.kwargs = kwargs
        self.signals = WorkerSignals()

    @pyqtSlot()
    def run(self):
        try:
            result = self.function(*self.args, **self.kwargs)
        except Exception as exc:
            logging.getLogger(__name__).error(
                "Background task failed: %s\n%s", exc, traceback.format_exc()
            )
            self.signals.failed.emit(str(exc) or "عملیات با خطا مواجه شد.")
        else:
            self.signals.succeeded.emit(result)
        finally:
            self.signals.finished.emit()

