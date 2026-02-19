from __future__ import annotations

import logging
import re
from logging.handlers import RotatingFileHandler
from pathlib import Path


class SensitiveDataFilter(logging.Filter):
    """Redact common token-like patterns from log messages."""

    _patterns = [
        re.compile(r"bot\d{8,}:[A-Za-z0-9_-]{20,}"),
        re.compile(r"sk-[A-Za-z0-9]{16,}"),
        re.compile(r"\b\d{8,}:[A-Za-z0-9_-]{20,}\b"),
    ]

    def filter(self, record: logging.LogRecord) -> bool:
        message = record.getMessage()
        for pattern in self._patterns:
            message = pattern.sub("[REDACTED]", message)
        record.msg = message
        record.args = ()
        return True


def setup_logging(level: str = "INFO", log_file: str | None = "logs/bot.log") -> None:
    root_logger = logging.getLogger()
    root_logger.setLevel(level)

    formatter = logging.Formatter(
        fmt="%(asctime)s %(levelname)s [%(name)s] %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )

    root_logger.handlers.clear()

    stream_handler = logging.StreamHandler()
    stream_handler.setFormatter(formatter)
    stream_handler.addFilter(SensitiveDataFilter())
    root_logger.addHandler(stream_handler)

    if log_file:
        log_path = Path(log_file)
        log_path.parent.mkdir(parents=True, exist_ok=True)
        file_handler = RotatingFileHandler(
            log_path,
            maxBytes=1_000_000,
            backupCount=3,
            encoding="utf-8",
        )
        file_handler.setFormatter(formatter)
        file_handler.addFilter(SensitiveDataFilter())
        root_logger.addHandler(file_handler)

    # Prevent request URLs (which can include bot tokens) from being logged.
    for noisy_logger_name in ("httpx", "httpx._client", "httpcore"):
        noisy_logger = logging.getLogger(noisy_logger_name)
        noisy_logger.handlers.clear()
        noisy_logger.setLevel(logging.WARNING)
        noisy_logger.propagate = False
