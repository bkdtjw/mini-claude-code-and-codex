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
    stdout_handler = logging.StreamHandler(_StdoutProxy())
    stdout_handler.setFormatter(formatter)
    file_handler = build_file_handler(formatter)
    root_logger = logging.getLogger()
    root_logger.handlers.clear()
    root_logger.addHandler(stdout_handler)
    root_logger.addHandler(file_handler)
    root_logger.setLevel(getattr(logging, log_level.strip().upper(), logging.INFO))
    _LOGGING_CONFIGURED = True


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
    "setup_logging",
]
