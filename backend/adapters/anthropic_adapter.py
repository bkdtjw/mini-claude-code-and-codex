from __future__ import annotations

import asyncio
import json
from collections.abc import AsyncIterator
from typing import Any

import httpx

from backend.adapters.base import LLMAdapter
from backend.common import LLMError
from backend.common.types import LLMRequest, LLMResponse, LLMUsage, Message, ProviderConfig, StreamChunk, ToolCall, ToolDefinition
from backend.config.http_client import load_http_client_config


class AnthropicAdapter(LLMAdapter):
    def __init__(self, config: ProviderConfig) -> None:
        base_url = config.base_url.rstrip("/") if config.base_url else "https://api.anthropic.com/v1"
        self._api_key = config.api_key
        self._url = base_url if base_url.endswith("/messages") else f"{base_url}/messages"
        self._provider = config.provider_type.value
        self._default_model = config.default_model
        self._extra_headers = dict(config.extra_headers)
        self._max_retries = 3

    async def test_connection(self) -> bool:
        try:
            payload = {
                "model": self._default_model,
                "max_tokens": 1,
                "messages": [{"role": "user", "content": [{"type": "text", "text": "ping"}]}],
            }
            async with httpx.AsyncClient(timeout=15.0, trust_env=load_http_client_config().trust_env) as client:
                response = await client.post(self._url, headers=self._headers(), json=payload)
            self._raise_for_status(response)
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
                    await asyncio.sleep(float(attempt))
                    continue
                self._raise_for_status(response)
                return self._parse_response(response.json())
            raise LLMError("RATE_LIMIT", "Anthropic rate limited", self._provider, 429)
        except LLMError:
            raise
        except httpx.RequestError as exc:
            raise LLMError("NETWORK_ERROR", str(exc), self._provider, None) from exc
        except Exception as exc:
            raise LLMError("COMPLETE_ERROR", str(exc), self._provider, None) from exc

    async def stream(self, request: LLMRequest) -> AsyncIterator[StreamChunk]:
        try:
            payload = self._build_payload(request, stream=True)
            for attempt in range(1, self._max_retries + 1):
                async with httpx.AsyncClient(timeout=60.0, trust_env=load_http_client_config().trust_env) as client:
                    async with client.stream("POST", self._url, headers=self._headers(), json=payload) as response:
                        if response.status_code == 429 and attempt < self._max_retries:
                            await asyncio.sleep(float(attempt))
                            continue
                        self._raise_for_status(response)
                        event_type = ""
                        async for line in response.aiter_lines():
                            if line.startswith("event:"):
                                event_type = line.split(":", 1)[1].strip()
                                continue
                            if not line.startswith("data:"):
                                continue
                            chunk = self._parse_stream_line(event_type, line.split(":", 1)[1].strip())
                            if chunk is None:
                                continue
                            yield chunk
                            if chunk.type == "done":
                                return
                        yield StreamChunk(type="done")
                        return
            raise LLMError("RATE_LIMIT", "Anthropic rate limited", self._provider, 429)
        except LLMError:
            raise
        except httpx.RequestError as exc:
            raise LLMError("NETWORK_ERROR", str(exc), self._provider, None) from exc
        except Exception as exc:
            raise LLMError("STREAM_ERROR", str(exc), self._provider, None) from exc

    def _build_payload(self, request: LLMRequest, stream: bool) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "model": request.model,
            "messages": self._to_anthropic_messages(request.messages),
            "max_tokens": request.max_tokens,
            "temperature": request.temperature,
        }
        if request.tools:
            payload["tools"] = self._to_anthropic_tools(request.tools)
        if stream:
            payload["stream"] = True
        return payload

    def _to_anthropic_messages(self, messages: list[Message]) -> list[dict[str, Any]]:
        result: list[dict[str, Any]] = []
        for msg in messages:
            if msg.role == "assistant":
                content = [block for block in msg.provider_metadata.get("thinking_blocks", []) if isinstance(block, dict)]
                if msg.content:
                    content.append({"type": "text", "text": msg.content})
                for call in msg.tool_calls or []:
                    content.append({"type": "tool_use", "id": call.id, "name": call.name, "input": call.arguments})
                result.append({"role": "assistant", "content": content or [{"type": "text", "text": ""}]})
            elif msg.role == "tool" and msg.tool_results:
                content = [{"type": "tool_result", "tool_use_id": res.tool_call_id, "content": res.output, "is_error": res.is_error} for res in msg.tool_results]
                result.append({"role": "user", "content": content})
            else:
                text = msg.content if msg.role != "system" else f"[system] {msg.content}"
                result.append({"role": "user", "content": [{"type": "text", "text": text}]})
        return result

    def _to_anthropic_tools(self, tools: list[ToolDefinition]) -> list[dict[str, Any]]:
        return [{"name": tool.name, "description": tool.description, "input_schema": tool.parameters.model_dump()} for tool in tools]

    def _parse_response(self, data: dict[str, Any]) -> LLMResponse:
        content_blocks = data.get("content", [])
        content = "".join(block.get("text", "") for block in content_blocks if block.get("type") == "text")
        tool_calls = [ToolCall(id=block.get("id", ""), name=block.get("name", ""), arguments=block.get("input", {})) for block in content_blocks if block.get("type") == "tool_use"]
        usage = data.get("usage", {})
        provider_metadata: dict[str, Any] = {}
        thinking_blocks = [block for block in content_blocks if block.get("type") == "thinking"]
        if thinking_blocks:
            provider_metadata["thinking_blocks"] = thinking_blocks
            provider_metadata["thinking"] = "".join(str(block.get("thinking", "")) for block in thinking_blocks)
        return LLMResponse(
            id=data.get("id", ""),
            content=content,
            tool_calls=tool_calls,
            usage=LLMUsage(prompt_tokens=usage.get("input_tokens", 0), completion_tokens=usage.get("output_tokens", 0)),
            provider_metadata=provider_metadata,
        )

    def _parse_stream_line(self, event_type: str, raw: str) -> StreamChunk | None:
        if raw == "[DONE]" or event_type == "message_stop":
            return StreamChunk(type="done")
        try:
            data = json.loads(raw)
        except json.JSONDecodeError:
            return None
        if event_type == "content_block_delta":
            delta = data.get("delta", {})
            text = delta.get("text", "") if delta.get("type") == "text_delta" else ""
            return StreamChunk(type="text", data=text) if text else None
        if event_type == "content_block_start":
            block = data.get("content_block", {})
            if block.get("type") == "tool_use":
                return StreamChunk(type="tool_call", data={"id": block.get("id", ""), "name": block.get("name", ""), "arguments": block.get("input", {})})
        if event_type == "error":
            detail = data.get("error", {}).get("message", str(data))
            raise LLMError("STREAM_ERROR", detail, self._provider, None)
        return None

    def _headers(self) -> dict[str, str]:
        return {
            "x-api-key": self._api_key,
            "anthropic-version": "2023-06-01",
            "content-type": "application/json",
            **self._extra_headers,
        }

    def _raise_for_status(self, response: httpx.Response) -> None:
        if response.status_code == 401:
            raise LLMError("AUTH_ERROR", "Invalid Anthropic API key", self._provider, 401)
        if response.status_code == 500:
            raise LLMError("SERVER_ERROR", "Anthropic server error", self._provider, 500)
        if response.status_code >= 400:
            raise LLMError("API_ERROR", self._error_message(response), self._provider, response.status_code)

    def _error_message(self, response: httpx.Response) -> str:
        try:
            return response.json().get("error", {}).get("message", response.text)
        except Exception:
            return response.text
