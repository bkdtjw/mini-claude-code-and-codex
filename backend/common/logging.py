from __future__ import annotations

import logging
import os
import sys
from collections.abc import Generator
from contextlib import contextmanager
from typing import Any
from uuid import uuid4

import structlog

from .log_file_support import build_file_handler

_WORKER_ID = f"worker-{os.getpid()}-{uuid4().hex[:8]}"
_LOGGING_CONFIGURED = False
_FALSE_VALUES = {"0", "false", "no", "off"}
_SENSITIVE_KEY_PARTS = ("api_key", "authorization", "cookie", "password", "secret", "token")
_REDACTED = "[redacted]"


class _StdoutProxy:
    def write(self, message: str) -> int:
        return sys.stdout.write(message)

    def flush(self) -> None:
        sys.stdout.flush()


def get_worker_id() -> str:
    return _WORKER_ID


def new_trace_id() -> str:
    return uuid4().hex[:12]


def setup_logging(log_level: str = "INFO") -> None:
    global _LOGGING_CONFIGURED
    shared_processors = [
        structlog.contextvars.merge_contextvars,
        structlog.stdlib.add_logger_name,
        structlog.stdlib.add_log_level,
        structlog.processors.TimeStamper(fmt="iso", utc=True),
        redact_sensitive_fields,
    ]
    renderer: structlog.types.Processor = structlog.processors.JSONRenderer()
    if os.getenv("LOG_FORMAT", "json").strip().lower() == "console":
        renderer = structlog.dev.ConsoleRenderer(colors=False)
    structlog.configure(
        processors=[
            *shared_processors,
            structlog.stdlib.PositionalArgumentsFormatter(),
            structlog.processors.StackInfoRenderer(),
            structlog.processors.format_exc_info,
            structlog.stdlib.ProcessorFormatter.wrap_for_formatter,
        ],
        logger_factory=structlog.stdlib.LoggerFactory(),
        wrapper_class=structlog.stdlib.BoundLogger,
        cache_logger_on_first_use=True,
    )
    formatter = structlog.stdlib.ProcessorFormatter(
        foreign_pre_chain=shared_processors,
        processors=[
            structlog.stdlib.ProcessorFormatter.remove_processors_meta,
            structlog.processors.format_exc_info,
            renderer,
        ],
    )
    root_logger = logging.getLogger()
    root_logger.handlers.clear()
    if _stdout_logging_enabled():
        stdout_handler = logging.StreamHandler(_StdoutProxy())
        stdout_handler.setFormatter(formatter)
        root_logger.addHandler(stdout_handler)
    if _file_logging_enabled():
        root_logger.addHandler(build_file_handler(formatter, get_worker_id()))
    root_logger.setLevel(getattr(logging, log_level.strip().upper(), logging.INFO))
    _LOGGING_CONFIGURED = True


def _stdout_logging_enabled() -> bool:
    return os.getenv("LOG_STDOUT", "1").strip().lower() not in _FALSE_VALUES


def _file_logging_enabled() -> bool:
    return os.getenv("LOG_FILE_ENABLED", "1").strip().lower() not in _FALSE_VALUES


def redact_sensitive_fields(
    _logger: Any,
    _method_name: str,
    event_dict: dict[str, Any],
) -> dict[str, Any]:
    return {key: _redact_value(key, value) for key, value in event_dict.items()}


def _redact_value(key: str, value: Any) -> Any:
    if _is_sensitive_key(key):
        return _REDACTED
    if isinstance(value, dict):
        return {
            item_key: _redact_value(str(item_key), item_value)
            for item_key, item_value in value.items()
        }
    if isinstance(value, list):
        return [_redact_value(key, item) for item in value]
    return value


def _is_sensitive_key(key: str) -> bool:
    key_lower = key.lower()
    return any(part in key_lower for part in _SENSITIVE_KEY_PARTS)


def get_logger(**initial_values: Any) -> structlog.stdlib.BoundLogger:
    if not _LOGGING_CONFIGURED:
        setup_logging(os.getenv("LOG_LEVEL", "INFO"))
    values = {
        key: value
        for key, value in {"worker_id": get_worker_id(), **initial_values}.items()
        if value not in {"", None}
    }
    return structlog.get_logger().bind(**values)


def get_log_context() -> dict[str, Any]:
    return dict(structlog.contextvars.get_contextvars())


@contextmanager
def bound_log_context(**values: Any) -> Generator[None, None, None]:
    clean_values = {key: value for key, value in values.items() if value not in {"", None}}
    with structlog.contextvars.bound_contextvars(**clean_values):
        yield


__all__ = [
    "bound_log_context",
    "get_log_context",
    "get_logger",
    "get_worker_id",
    "new_trace_id",
    "redact_sensitive_fields",
    "setup_logging",
]
