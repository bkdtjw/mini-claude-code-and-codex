from __future__ import annotations

from backend.adapters.openai_adapter import OpenAICompatAdapter
from backend.common.types import LLMRequest, Message, ProviderConfig, ProviderType


def _adapter() -> OpenAICompatAdapter:
    provider = ProviderConfig(
        id="kimi-id",
        name="Kimi",
        provider_type=ProviderType.OPENAI_COMPAT,
        base_url="https://api.moonshot.cn/v1",
        api_key="",
        default_model="kimi-k2.6",
        available_models=["kimi-k2.6"],
        extra_body={"thinking": {"type": "enabled"}},
    )
    return OpenAICompatAdapter(provider)


def _request(thinking: bool) -> LLMRequest:
    return LLMRequest(
        model="kimi-k2.6",
        messages=[Message(role="user", content="hello")],
        thinking=thinking,
    )


def test_kimi_low_or_medium_disables_thinking() -> None:
    payload = _adapter()._build_payload(_request(thinking=False), stream=True)  # noqa: SLF001
    assert payload["stream"] is True
    assert payload["thinking"] == {"type": "disabled"}
    assert "enable_thinking" not in payload


def test_kimi_high_enables_thinking() -> None:
    payload = _adapter()._build_payload(_request(thinking=True), stream=True)  # noqa: SLF001
    assert payload["thinking"] == {"type": "enabled"}
    assert payload["temperature"] == 1.0
    assert payload["max_tokens"] >= 16000
    assert "enable_thinking" not in payload
