from __future__ import annotations

import base64
import hashlib
import hmac
import os
import time
from typing import Any

import httpx

from backend.common.feishu_markdown import strip_markdown_for_feishu
from backend.common.types import ToolDefinition, ToolExecuteFn, ToolParameterSchema, ToolResult

REQUEST_TIMEOUT_SECONDS = 10.0
MAX_FEISHU_CONTENT_LENGTH = 18000  # 20KB limit minus 2KB margin


def _truncate_content(content: str) -> str:
    if len(content.encode("utf-8")) <= MAX_FEISHU_CONTENT_LENGTH:
        return content
    truncated = content[: MAX_FEISHU_CONTENT_LENGTH // 3]
    return f"{truncated}\n\n...[消息过长，已截断]"


def _generate_sign(secret: str) -> tuple[str, str]:
    timestamp = str(int(time.time()))
    string_to_sign = f"{timestamp}\n{secret}"
    hmac_code = hmac.new(
        string_to_sign.encode("utf-8"),
        digestmod=hashlib.sha256,
    ).digest()
    sign = base64.b64encode(hmac_code).decode("utf-8")
    return timestamp, sign


def create_feishu_notify_tool(
    webhook_url: str | None = None,
    secret: str | None = None,
) -> tuple[ToolDefinition, ToolExecuteFn]:
    definition = ToolDefinition(
        name="feishu_notify",
        description="Send a message to a Feishu bot webhook.",
        category="shell",
        parameters=ToolParameterSchema(
            properties={
                "content": {"type": "string", "description": "Message body"},
                "title": {
                    "type": "string",
                    "description": "Optional rich-text title",
                },
            },
            required=["content"],
        ),
    )
    resolved_url = (webhook_url or os.environ.get("FEISHU_WEBHOOK_URL", "")).strip()

    async def execute(args: dict[str, Any]) -> ToolResult:
        try:
            content = str(args.get("content", "")).strip()
            if not content:
                return ToolResult(output="content cannot be empty", is_error=True)
            if not resolved_url:
                return ToolResult(output="FEISHU_WEBHOOK_URL is not configured", is_error=True)
            title = str(args.get("title", "")).strip()
            content = _truncate_content(content)
            body = _build_request_body(content=content, title=title, secret=secret)
            try:
                async with httpx.AsyncClient(
                    timeout=REQUEST_TIMEOUT_SECONDS,
                    trust_env=False,
                ) as client:
                    response = await client.post(resolved_url, json=body)
            except httpx.HTTPError as exc:
                return ToolResult(output=f"Feishu request failed: {exc}", is_error=True)
            if response.status_code >= 400:
                return ToolResult(
                    output=f"Feishu request failed with HTTP {response.status_code}",
                    is_error=True,
                )
            try:
                data = response.json()
            except ValueError:
                return ToolResult(
                    output="Feishu request failed: response is not valid JSON",
                    is_error=True,
                )
            if data.get("StatusCode", data.get("code")) == 0:
                label = title or "(text)"
                return ToolResult(output=f"Feishu message sent: {label}")
            error_message = data.get("StatusMessage", data.get("msg", str(data)))
            return ToolResult(output=f"Feishu request failed: {error_message}", is_error=True)
        except Exception as exc:  # noqa: BLE001
            return ToolResult(output=str(exc), is_error=True)

    return definition, execute


def _build_request_body(content: str, title: str, secret: str | None) -> dict[str, Any]:
    content = strip_markdown_for_feishu(content)
    if title:
        body: dict[str, Any] = {
            "msg_type": "post",
            "content": {
                "post": {
                    "zh_cn": {
                        "title": title,
                        "content": [[{"tag": "text", "text": content}]],
                    }
                }
            },
        }
    else:
        body = {"msg_type": "text", "content": {"text": content}}
    if secret:
        timestamp, sign = _generate_sign(secret)
        body["timestamp"] = timestamp
        body["sign"] = sign
    return body


__all__ = ["create_feishu_notify_tool"]
