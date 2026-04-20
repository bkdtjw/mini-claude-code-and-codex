from __future__ import annotations

import logging
import os
from logging.handlers import TimedRotatingFileHandler
from pathlib import Path

DEFAULT_LOG_DIR = "/app/data/logs"
DEFAULT_LOG_RETENTION_DAYS = 7
DEFAULT_LOG_FALLBACK_DIR = "/tmp/agent-studio-logs"
LOG_FILE_NAME = "app.log"


class DailyLogFileHandler(TimedRotatingFileHandler):
    def rotation_filename(self, default_name: str) -> str:
        path = Path(default_name)
        date_suffix = path.name.removeprefix(f"{LOG_FILE_NAME}.")
        return str(path.with_name(f"app.{date_suffix}.log"))

    def getFilesToDelete(self) -> list[str]:
        directory = Path(self.baseFilename).parent
        backups = sorted(directory.glob("app.????-??-??.log"))
        if self.backupCount <= 0 or len(backups) <= self.backupCount:
            return []
        return [str(path) for path in backups[: len(backups) - self.backupCount]]


def get_log_file_dir() -> Path:
    return Path(os.getenv("LOG_FILE_DIR", DEFAULT_LOG_DIR)).expanduser()


def get_log_retention_days() -> int:
    raw = os.getenv("LOG_FILE_RETENTION_DAYS", str(DEFAULT_LOG_RETENTION_DAYS)).strip()
    try:
        return max(int(raw), 1)
    except ValueError:
        return DEFAULT_LOG_RETENTION_DAYS


def get_current_log_file() -> Path:
    return ensure_log_file_dir() / LOG_FILE_NAME


def ensure_log_file_dir() -> Path:
    preferred = get_log_file_dir()
    try:
        preferred.mkdir(parents=True, exist_ok=True)
        return preferred
    except OSError:
        fallback = Path(os.getenv("LOG_FILE_FALLBACK_DIR", DEFAULT_LOG_FALLBACK_DIR)).expanduser()
        fallback.mkdir(parents=True, exist_ok=True)
        return fallback


def build_file_handler(formatter: logging.Formatter) -> logging.Handler:
    log_dir = ensure_log_file_dir()
    handler = DailyLogFileHandler(
        filename=str(log_dir / LOG_FILE_NAME),
        when="midnight",
        backupCount=get_log_retention_days(),
        encoding="utf-8",
        utc=True,
    )
    handler.setFormatter(formatter)
    return handler


__all__ = [
    "DEFAULT_LOG_DIR",
    "DEFAULT_LOG_FALLBACK_DIR",
    "DEFAULT_LOG_RETENTION_DAYS",
    "LOG_FILE_NAME",
    "DailyLogFileHandler",
    "build_file_handler",
    "ensure_log_file_dir",
    "get_current_log_file",
    "get_log_file_dir",
    "get_log_retention_days",
]
