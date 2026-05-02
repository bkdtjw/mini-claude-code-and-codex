from __future__ import annotations

import httpx
import pytest

from backend.adapters.openai_adapter import OpenAICompatAdapter
from backend.common import LLMError
from backend.common.types import ProviderConfig, ProviderType


def _adapter() -> OpenAICompatAdapter:
    return OpenAICompatAdapter(
        ProviderConfig(
            id="zhipu",
            name="zhipu",
            provider_type=ProviderType.OPENAI_COMPAT,
            base_url="https://open.bigmodel.cn/api/paas/v4",
            api_key="",
            default_model="glm-5.1",
        )
    )


def _response(payload: dict[str, object]) -> httpx.Response:
    return httpx.Response(
        429,
        json=payload,
        request=httpx.Request("POST", "https://open.bigmodel.cn/api/paas/v4/chat/completions"),
    )


def test_openai_adapter_preserves_provider_rate_limit_code() -> None:
    response = _response(
        {"error": {"code": "1302", "message": "您的账户已达到速率限制，请您控制请求频率"}}
    )

    with pytest.raises(LLMError) as exc_info:
        _adapter()._raise_for_status(response)  # noqa: SLF001

    assert exc_info.value.code == "RATE_LIMIT_1302"
    assert exc_info.value.message == "您的账户已达到速率限制，请您控制请求频率"
    assert exc_info.value.status_code == 429


def test_openai_adapter_rate_limit_falls_back_for_unknown_body() -> None:
    with pytest.raises(LLMError) as exc_info:
        _adapter()._raise_for_status(_response({"detail": "too many requests"}))  # noqa: SLF001

    assert exc_info.value.code == "RATE_LIMIT"
    assert exc_info.value.message == "Provider rate limited"
