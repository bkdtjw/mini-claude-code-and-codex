from __future__ import annotations

from backend.adapters.anthropic_adapter import AnthropicAdapter
from backend.adapters.ollama_adapter import OllamaAdapter
from backend.adapters.openai_adapter import OpenAICompatAdapter
from backend.common.types import Message, ProviderConfig, ProviderType


def _provider(provider_type: ProviderType) -> ProviderConfig:
    return ProviderConfig(
        id=f"{provider_type.value}-id",
        name=provider_type.value,
        provider_type=provider_type,
        base_url="https://example.com",
        api_key="",
        default_model="test-model",
        available_models=["test-model"],
    )


def test_openai_adapter_round_trips_reasoning_content() -> None:
    adapter = OpenAICompatAdapter(_provider(ProviderType.OPENAI_COMPAT))
    messages = adapter._to_openai_messages([Message(role="assistant", content="answer", provider_metadata={"reasoning_content": "step"})])  # noqa: SLF001
    response = adapter._parse_response(  # noqa: SLF001
        {
            "id": "resp-1",
            "choices": [{"message": {"content": "answer", "reasoning_content": "step"}}],
            "usage": {"prompt_tokens": 1, "completion_tokens": 2},
        }
    )
    assert messages[0]["reasoning_content"] == "step"
    assert response.provider_metadata["reasoning_content"] == "step"


def test_anthropic_adapter_round_trips_thinking_blocks() -> None:
    adapter = AnthropicAdapter(_provider(ProviderType.ANTHROPIC))
    messages = adapter._to_anthropic_messages(  # noqa: SLF001
        [Message(role="assistant", content="answer", provider_metadata={"thinking_blocks": [{"type": "thinking", "thinking": "step"}]})]
    )
    response = adapter._parse_response(  # noqa: SLF001
        {
            "id": "resp-2",
            "content": [{"type": "thinking", "thinking": "step"}, {"type": "text", "text": "answer"}],
            "usage": {"input_tokens": 1, "output_tokens": 2},
        }
    )
    assert messages[0]["content"][0]["type"] == "thinking"
    assert response.provider_metadata["thinking"] == "step"
    assert response.provider_metadata["thinking_blocks"][0]["type"] == "thinking"


def test_ollama_adapter_parses_reasoning_content() -> None:
    adapter = OllamaAdapter(_provider(ProviderType.OLLAMA))
    response = adapter._parse_response(  # noqa: SLF001
        {"message": {"content": "answer", "reasoning_content": "step"}, "prompt_eval_count": 1, "eval_count": 2}
    )
    assert response.provider_metadata["reasoning_content"] == "step"
