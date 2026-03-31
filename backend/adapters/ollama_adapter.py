from __future__ import annotations
import asyncio, json
from collections.abc import AsyncIterator; from typing import Any
import httpx
from backend.common import LLMError
from backend.common.types import LLMRequest, LLMResponse, LLMUsage, ProviderConfig, StreamChunk, ToolCall
from backend.config.http_client import load_http_client_config
from .openai_adapter import OpenAICompatAdapter
class OllamaAdapter(OpenAICompatAdapter):
    """本地 Ollama 适配器"""
    def __init__(self, config: ProviderConfig) -> None:
        super().__init__(config)
        base = (config.base_url or "http://localhost:11434").rstrip("/")
        root = base[:-9] if base.endswith("/api/chat") else base[:-4] if base.endswith("/api") else base
        self._url = base if base.endswith("/api/chat") else (f"{base}/chat" if base.endswith("/api") else f"{base}/api/chat")
        self._tags_url = f"{root}/api/tags"
        self._api_key = ""
        self._provider = "ollama"
    async def test_connection(self) -> bool:
        try:
            async with httpx.AsyncClient(timeout=10.0, trust_env=load_http_client_config().trust_env) as client:
                response = await client.get(self._tags_url, headers=self._headers())
            return response.is_success
        except Exception:
            return False
    async def complete(self, request: LLMRequest) -> LLMResponse:
        try:
            payload = self._build_payload(request, stream=False)
            for attempt in range(1, self._max_retries + 1):
                async with httpx.AsyncClient(timeout=60.0, trust_env=load_http_client_config().trust_env) as client:
                    response = await client.post(self._url, headers=self._headers(), json=payload)
                if response.status_code == 429 and attempt < self._max_retries:
                    await asyncio.sleep(float(attempt)); continue
                if response.status_code == 429:
                    raise LLMError("RATE_LIMIT", "Ollama rate limited", self._provider, 429)
                self._raise_for_status(response)
                return self._parse_response(response.json())
            raise LLMError("RATE_LIMIT", "Ollama rate limited", self._provider, 429)
        except LLMError:
            raise
        except httpx.RequestError as exc:
            raise LLMError("NETWORK_ERROR", str(exc), self._provider, None) from exc
        except Exception as exc:
            raise LLMError("COMPLETE_ERROR", str(exc), self._provider, None) from exc
    async def stream(self, request: LLMRequest) -> AsyncIterator[StreamChunk]:
        try:
            payload = self._build_payload(request, stream=True)
            async with httpx.AsyncClient(timeout=60.0, trust_env=load_http_client_config().trust_env) as client:
                async with client.stream("POST", self._url, headers=self._headers(), json=payload) as response:
                    self._raise_for_status(response)
                    async for line in response.aiter_lines():
                        raw = line.split(":", 1)[1].strip() if line.startswith("data:") else line.strip()
                        if not raw:
                            continue
                        data = json.loads(raw)
                        msg = data.get("message", {})
                        if msg.get("content"):
                            yield StreamChunk(type="text", data=msg["content"])
                        for tc in msg.get("tool_calls", []) or []:
                            fn = tc.get("function", {})
                            yield StreamChunk(type="tool_call", data={"id": tc.get("id", ""), "name": fn.get("name", ""), "arguments": fn.get("arguments", {})})
                        if data.get("done"):
                            yield StreamChunk(type="done"); return
                    yield StreamChunk(type="done")
        except LLMError:
            raise
        except httpx.RequestError as exc:
            raise LLMError("NETWORK_ERROR", str(exc), self._provider, None) from exc
        except Exception as exc:
            raise LLMError("STREAM_ERROR", str(exc), self._provider, None) from exc
    def _build_payload(self, request: LLMRequest, stream: bool) -> dict[str, Any]:
        payload: dict[str, Any] = {"model": request.model or self._default_model, "messages": self._to_openai_messages(request.messages), "stream": stream, "options": {"temperature": request.temperature, "num_predict": request.max_tokens}}
        if request.tools:
            payload["tools"] = self._to_openai_tools(request.tools)
        return payload
    def _parse_response(self, data: dict[str, Any]) -> LLMResponse:
        msg, usage = data.get("message", {}), data
        calls = [ToolCall(id=tc.get("id", ""), name=tc.get("function", {}).get("name", ""), arguments=tc.get("function", {}).get("arguments", {}) or {}) for tc in msg.get("tool_calls", []) or []]
        provider_metadata: dict[str, Any] = {}
        reasoning = msg.get("reasoning_content")
        if isinstance(reasoning, str) and reasoning:
            provider_metadata["reasoning_content"] = reasoning
        return LLMResponse(
            content=msg.get("content", "") or "",
            tool_calls=calls,
            usage=LLMUsage(prompt_tokens=usage.get("prompt_eval_count", 0), completion_tokens=usage.get("eval_count", 0)),
            provider_metadata=provider_metadata,
        )
    def _headers(self) -> dict[str, str]:
        return {"content-type": "application/json", **self._extra_headers}
