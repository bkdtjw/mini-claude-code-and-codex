from __future__ import annotations

import logging
import re

_KEY_RE = re.compile(r"([?&](?:key|app_key|appkey|access_token|sign|360buy_param_json)=)[^&\s]+")


class ApiKeyRedactionFilter(logging.Filter):
    """Redact Google API keys from httpx request logs."""

    def filter(self, record: logging.LogRecord) -> bool:
        record.msg = _redact_value(record.msg)
        if isinstance(record.args, tuple):
            record.args = tuple(_redact_value(item) for item in record.args)
        elif isinstance(record.args, dict):
            record.args = {key: _redact_value(value) for key, value in record.args.items()}
        return True


def install_httpx_api_key_redaction() -> None:
    logger = logging.getLogger("httpx")
    if any(isinstance(item, ApiKeyRedactionFilter) for item in logger.filters):
        return
    logger.addFilter(ApiKeyRedactionFilter())


def _redact_value(value: object) -> object:
    text = str(value)
    if not any(marker in text for marker in ("key=", "app_key=", "appkey=", "access_token=", "sign=")):
        return value
    return _KEY_RE.sub(r"\1<redacted>", text)


__all__ = ["install_httpx_api_key_redaction"]
