from __future__ import annotations

from collections.abc import Generator

import pytest

from backend.config.settings import settings


@pytest.fixture(autouse=True)
def reset_feishu_settings() -> Generator[None, None, None]:
    original_url = settings.feishu_webhook_url
    original_secret = settings.feishu_webhook_secret
    settings.feishu_webhook_url = ""
    settings.feishu_webhook_secret = ""
    yield
    settings.feishu_webhook_url = original_url
    settings.feishu_webhook_secret = original_secret
