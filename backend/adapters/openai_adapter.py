from __future__ import annotations
import asyncio, json
from collections.abc import AsyncIterator; from typing import Any
import httpx
from backend.adapters.base import LLMAdapter
from backend.common import LLMError
from backend.common.types import LLMRequest, LLMResponse, LLMUsage, Message, ProviderConfig, StreamChunk, ToolCall, ToolDefinition
from backend.config.http_client import load_http_client_config
class OpenAICompatAdapter(LLMAdapter):
    """OpenAI/Kimi/GLM/DeepSeek/Lingyi/Qwen/any OpenAI-compatible endpoint adapter."""
    def __init__(self, config: ProviderConfig) -> None:
        self._provider = config.provider_type.value
        self._url = f"{config.base_url.rstrip('/')}/chat/completions"
        self._api_key = config.api_key
        self._default_model = config.default_model
        self._extra_headers = dict(config.extra_headers)
        self._max_retries = 3
    async def test_connection(self) -> bool:
        try:
            payload = {"model": self._default_model, "messages": [{"role": "user", "content": "ping"}], "max_tokens": 1}
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
                if response.status_code == 429:
                    if attempt < self._max_retries:
                        await asyncio.sleep(float(attempt))
                        continue
                    raise LLMError("RATE_LIMIT", "Provider rate limited", self._provider, 429)
                self._raise_for_status(response)
                return self._parse_response(response.json())
            raise LLMError("RATE_LIMIT", "Provider rate limited", self._provider, 429)
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
                        if response.status_code == 429:
                            if attempt < self._max_retries:
                                await asyncio.sleep(float(attempt))
                                continue
                            raise LLMError("RATE_LIMIT", "Provider rate limited", self._provider, 429)
                        self._raise_for_status(response)
                        tool_chunks: dict[int, dict[str, str]] = {}
                        async for line in response.aiter_lines():
                            if not line.startswith("data:"):
                                continue
                            raw = line.split(":", 1)[1].strip()
                            if raw == "[DONE]":
                                for chunk in self._flush_tool_calls(tool_chunks):
                                    yield chunk
                                yield StreamChunk(type="done")
                                return
                            for chunk in self._parse_stream_line(raw, tool_chunks):
                                yield chunk
                        for chunk in self._flush_tool_calls(tool_chunks):
                            yield chunk
                        yield StreamChunk(type="done")
                        return
            raise LLMError("RATE_LIMIT", "Provider rate limited", self._provider, 429)
        except LLMError:
            raise
        except httpx.RequestError as exc:
            raise LLMError("NETWORK_ERROR", str(exc), self._provider, None) from exc
        except Exception as exc:
            raise LLMError("STREAM_ERROR", str(exc), self._provider, None) from exc
    def _build_payload(self, request: LLMRequest, stream: bool) -> dict[str, Any]:
        payload: dict[str, Any] = {"model": request.model or self._default_model, "messages": self._to_openai_messages(request.messages), "temperature": request.temperature, "max_tokens": request.max_tokens}
        if request.tools:
            payload["tools"] = self._to_openai_tools(request.tools)
        if stream:
            payload["stream"] = True
        return payload
    def _to_openai_messages(self, messages: list[Message]) -> list[dict[str, Any]]:
        result: list[dict[str, Any]] = []
        for msg in messages:
            if msg.role == "assistant":
                item: dict[str, Any] = {"role": "assistant", "content": msg.content}
                reasoning = msg.provider_metadata.get("reasoning_content")
                if isinstance(reasoning, str) and reasoning:
                    item["reasoning_content"] = reasoning
                if msg.tool_calls:
                    item["tool_calls"] = [{"id": c.id, "type": "function", "function": {"name": c.name, "arguments": json.dumps(c.arguments, ensure_ascii=False)}} for c in msg.tool_calls]
                result.append(item)
            elif msg.role == "tool" and msg.tool_results:
                for res in msg.tool_results:
                    result.append({"role": "tool", "tool_call_id": res.tool_call_id, "content": res.output})
            else:
                role = msg.role if msg.role in {"system", "user"} else "user"
                result.append({"role": role, "content": msg.content})
        return result
    def _to_openai_tools(self, tools: list[ToolDefinition]) -> list[dict[str, Any]]:
        return [{"type": "function", "function": {"name": t.name, "description": t.description, "parameters": t.parameters.model_dump()}} for t in tools]
    def _parse_response(self, data: dict[str, Any]) -> LLMResponse:
        message = (data.get("choices") or [{}])[0].get("message", {})
        tool_calls = [ToolCall(id=tc.get("id", ""), name=tc.get("function", {}).get("name", ""), arguments=self._parse_args(tc.get("function", {}).get("arguments", ""))) for tc in message.get("tool_calls", []) or []]
        usage = data.get("usage", {})
        provider_metadata: dict[str, Any] = {}
        reasoning = message.get("reasoning_content")
        if isinstance(reasoning, str) and reasoning:
            provider_metadata["reasoning_content"] = reasoning
        return LLMResponse(
            id=data.get("id", ""),
            content=message.get("content", "") or "",
            tool_calls=tool_calls,
            usage=LLMUsage(prompt_tokens=usage.get("prompt_tokens", 0), completion_tokens=usage.get("completion_tokens", 0)),
            provider_metadata=provider_metadata,
        )
    def _parse_stream_line(self, raw: str, tool_chunks: dict[int, dict[str, str]]) -> list[StreamChunk]:
        try:
            data = json.loads(raw)
        except json.JSONDecodeError:
            return []
        choice = (data.get("choices") or [{}])[0]
        delta = choice.get("delta", {})
        for tc in delta.get("tool_calls", []) or []:
            idx = tc.get("index", 0)
            buf = tool_chunks.setdefault(idx, {"id": "", "name": "", "arguments": ""})
            buf["id"] = tc.get("id", buf["id"])
            func = tc.get("function", {})
            buf["name"] = func.get("name", buf["name"])
            buf["arguments"] += func.get("arguments", "")
        chunks = [StreamChunk(type="text", data=delta["content"])] if delta.get("content") else []
        if choice.get("finish_reason") == "tool_calls":
            chunks.extend(self._flush_tool_calls(tool_chunks))
        return chunks
    def _flush_tool_calls(self, tool_chunks: dict[int, dict[str, str]]) -> list[StreamChunk]:
        chunks = [StreamChunk(type="tool_call", data={"id": v["id"], "name": v["name"], "arguments": self._parse_args(v["arguments"])}) for _, v in sorted(tool_chunks.items()) if v["name"]]
        tool_chunks.clear()
        return chunks
    def _parse_args(self, raw: str) -> dict[str, Any]:
        try:
            return json.loads(raw) if raw else {}
        except json.JSONDecodeError:
            return {"raw": raw}
    def _headers(self) -> dict[str, str]:
        return {"content-type": "application/json", **self._extra_headers, **({"Authorization": f"Bearer {self._api_key}"} if self._api_key else {})}
    def _raise_for_status(self, response: httpx.Response) -> None:
        if response.status_code == 401:
            raise LLMError("AUTH_ERROR", "Invalid API key", self._provider, 401)
        if response.status_code == 500:
            raise LLMError("SERVER_ERROR", "Provider server error", self._provider, 500)
        if response.status_code >= 400:
            raise LLMError("API_ERROR", self._error_message(response), self._provider, response.status_code)
    def _error_message(self, response: httpx.Response) -> str:
        try:
            return response.json().get("error", {}).get("message", response.text)
        except Exception:
            return response.text
