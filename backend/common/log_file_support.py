from __future__ import annotations

import logging
import os
from logging.handlers import TimedRotatingFileHandler
from pathlib import Path
from typing import Any

DEFAULT_LOG_DIR = "/app/data/logs"
DEFAULT_LOG_RETENTION_DAYS = 7
DEFAULT_LOG_FALLBACK_DIR = "/tmp/agent-studio-logs"
LOG_FILE_NAME = "app.log"
_WORKER_SCOPE = "worker"


class DailyLogFileHandler(TimedRotatingFileHandler):
    def __init__(self, *args: Any, log_stem: str = "app", **kwargs: Any) -> None:
        self._log_stem = log_stem
        super().__init__(*args, **kwargs)

    def rotation_filename(self, default_name: str) -> str:
        path = Path(default_name)
        date_suffix = path.name.removeprefix(f"{self._log_stem}.log.")
        return str(path.with_name(f"{self._log_stem}.{date_suffix}.log"))

    def getFilesToDelete(self) -> list[str]:
        directory = Path(self.baseFilename).parent
        backups = sorted(directory.glob(f"{self._log_stem}.????-??-??.log"))
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


def get_log_file_stem(worker_id: str = "") -> str:
    if os.getenv("LOG_FILE_SCOPE", "").strip().lower() != _WORKER_SCOPE or not worker_id:
        return "app"
    safe_worker = "".join(char if char.isalnum() or char in {"-", "_"} else "-" for char in worker_id)
    return f"app.{safe_worker}"


def get_current_log_file(worker_id: str = "") -> Path:
    return ensure_log_file_dir() / f"{get_log_file_stem(worker_id)}.log"


def ensure_log_file_dir() -> Path:
    preferred = get_log_file_dir()
    try:
        preferred.mkdir(parents=True, exist_ok=True)
        return preferred
    except OSError:
        fallback = Path(os.getenv("LOG_FILE_FALLBACK_DIR", DEFAULT_LOG_FALLBACK_DIR)).expanduser()
        fallback.mkdir(parents=True, exist_ok=True)
        return fallback


def build_file_handler(formatter: logging.Formatter, worker_id: str = "") -> logging.Handler:
    log_dir = ensure_log_file_dir()
    log_stem = get_log_file_stem(worker_id)
    handler = DailyLogFileHandler(
        filename=str(log_dir / f"{log_stem}.log"),
        when="midnight",
        backupCount=get_log_retention_days(),
        encoding="utf-8",
        utc=True,
        log_stem=log_stem,
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
    "get_log_file_stem",
    "get_log_file_dir",
    "get_log_retention_days",
]
