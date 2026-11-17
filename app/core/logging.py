import logging
from logging.handlers import RotatingFileHandler


class DatabaseLogHandler(logging.Handler):
    def __init__(self, repository):
        super().__init__(logging.WARNING)
        self.repository = repository

    def emit(self, record):
        try:
            self.repository.append_log(
                record.levelname,
                record.name,
                self.format(record),
            )
        except Exception:
            self.handleError(record)


def configure_logging(log_dir, telemetry_repository=None):
    log_dir.mkdir(parents=True, exist_ok=True)
    handler = RotatingFileHandler(
        log_dir / "fittrack.log",
        maxBytes=2_000_000,
        backupCount=5,
        encoding="utf-8",
    )
    handler.setFormatter(
        logging.Formatter("%(asctime)s | %(levelname)s | %(name)s | %(message)s")
    )
    root = logging.getLogger()
    root.setLevel(logging.INFO)
    if not any(isinstance(item, RotatingFileHandler) for item in root.handlers):
        root.addHandler(handler)
    if telemetry_repository and not any(
        isinstance(item, DatabaseLogHandler) for item in root.handlers
    ):
        database_handler = DatabaseLogHandler(telemetry_repository)
        database_handler.setFormatter(logging.Formatter("%(message)s"))
        root.addHandler(database_handler)

