from __future__ import annotations

import logging

from backend.core.s02_tools.builtin.youtube_log_filter import install_httpx_api_key_redaction


def test_httpx_api_key_redaction_filter_masks_key(caplog) -> None:
    install_httpx_api_key_redaction()
    logger = logging.getLogger("httpx")

    with caplog.at_level(logging.INFO, logger="httpx"):
        logger.info("HTTP Request: GET %s", "https://example.test/path?part=x&key=secret123&x=1")

    assert "secret123" not in caplog.text
    assert "key=<redacted>" in caplog.text
