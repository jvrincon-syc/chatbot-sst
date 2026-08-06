from __future__ import annotations

import json
import logging
import sys
from datetime import datetime, timezone
from logging.handlers import RotatingFileHandler
from pathlib import Path
from typing import TextIO

from core.logging.observability import (
    sanitize_exception,
    sanitize_observability_payload,
)

_LOG_DIR = Path("logs")
_RESERVED_LOG_RECORD_ATTRS = frozenset(logging.makeLogRecord({}).__dict__) | {
    "asctime",
    "message",
}
_CONSOLE_HANDLER_NAME = "chatbot_sst_console"
_FILE_HANDLER_NAME = "chatbot_sst_file"


class StructuredJsonFormatter(logging.Formatter):
    """Format backend log records as structured JSON lines."""

    def format(self, record: logging.LogRecord) -> str:
        payload: dict[str, object] = {
            "timestamp": datetime.fromtimestamp(record.created, timezone.utc)
            .astimezone()
            .isoformat(),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
            "module": record.module,
            "line": record.lineno,
        }
        payload.update(_extra_fields(record))
        if record.exc_info:
            # Never emit a raw traceback: it can echo absolute paths, URLs,
            # provider response bodies or chained credential details. Only safe
            # class names, a redacted chained message and a correlation id go
            # out; the full diagnostic stays reproducible via internal_error_id.
            payload.update(sanitize_exception(record.exc_info))
        return json.dumps(payload, ensure_ascii=False, default=_json_default)


def _json_default(value: object) -> str:
    return str(value)


def _extra_fields(record: logging.LogRecord) -> dict[str, object]:
    sanitized = sanitize_observability_payload(
        {
            key: value
            for key, value in record.__dict__.items()
            if key not in _RESERVED_LOG_RECORD_ATTRS and not key.startswith("_")
        }
    )
    return {
        key: value
        for key, value in sanitized.items()
    }


def _has_named_handler(logger: logging.Logger, handler_name: str) -> bool:
    return any(handler.name == handler_name for handler in logger.handlers)


def get_logger(module_name: str) -> logging.Logger:
    """Return the configured backend logger for a module."""
    return _get_logger(module_name)


def configure_structured_logging(
    *,
    stream: TextIO = sys.stdout,
    include_file_handler: bool = True,
    log_path: Path | None = None,
) -> logging.Logger:
    """Configure the root logger for structured backend output."""

    return _configure_logger(
        logging.getLogger(),
        stream=stream,
        include_file_handler=include_file_handler,
        log_path=log_path,
    )


def _get_logger(name: str) -> logging.Logger:
    return _configure_logger(logging.getLogger(name), stream=sys.stdout)


def _configure_logger(
    logger: logging.Logger,
    *,
    stream: TextIO,
    include_file_handler: bool = True,
    log_path: Path | None = None,
) -> logging.Logger:
    logger.setLevel(logging.DEBUG)
    logger.propagate = False

    formatter = StructuredJsonFormatter()

    if not _has_named_handler(logger, _CONSOLE_HANDLER_NAME):
        console_handler = logging.StreamHandler(stream)
        console_handler.set_name(_CONSOLE_HANDLER_NAME)
        console_handler.setLevel(logging.INFO)
        console_handler.setFormatter(formatter)
        logger.addHandler(console_handler)

    if include_file_handler and not _has_named_handler(logger, _FILE_HANDLER_NAME):
        _LOG_DIR.mkdir(exist_ok=True)
        file_handler = RotatingFileHandler(
            log_path or (_LOG_DIR / "app.log"),
            maxBytes=5_000_000,
            backupCount=3,
            encoding="utf-8",
        )
        file_handler.set_name(_FILE_HANDLER_NAME)
        file_handler.setLevel(logging.WARNING)
        file_handler.setFormatter(formatter)
        logger.addHandler(file_handler)

    return logger
