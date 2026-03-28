from __future__ import annotations

import base64
import hashlib
import hmac
import os
import time
from typing import Any

import httpx

from backend.common.types import ToolDefinition, ToolExecuteFn, ToolParameterSchema, ToolResult


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
        description="发送消息到飞书群。支持纯文本和富文本格式。",
        category="shell",
        parameters=ToolParameterSchema(
            properties={
                "content": {"type": "string", "description": "消息正文内容"},
                "title": {"type": "string", "description": "消息标题（可选，填写后以富文本格式发送）"},
            },
            required=["content"],
        ),
    )
    default_url = webhook_url or os.environ.get("FEISHU_WEBHOOK_URL", "")

    async def execute(args: dict[str, Any]) -> ToolResult:
        try:
            content = str(args.get("content", "")).strip()
            if not content:
                return ToolResult(output="content 不能为空", is_error=True)
            url = default_url
            if not url:
                return ToolResult(output="未配置 FEISHU_WEBHOOK_URL", is_error=True)
            title = str(args.get("title", "")).strip()
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
                ts, sign = _generate_sign(secret)
                body["timestamp"] = ts
                body["sign"] = sign
            async with httpx.AsyncClient(timeout=10.0) as client:
                resp = await client.post(url, json=body)
            if resp.status_code >= 400:
                return ToolResult(output=f"飞书发送失败: HTTP {resp.status_code}", is_error=True)
            try:
                data = resp.json()
            except ValueError:
                return ToolResult(output="飞书发送失败: 响应不是有效 JSON", is_error=True)
            if data.get("StatusCode", data.get("code")) == 0:
                return ToolResult(output=f"飞书消息发送成功: {title or '(纯文本)'}")
            return ToolResult(
                output=f"飞书发送失败: {data.get('StatusMessage', data.get('msg', str(data)))}",
                is_error=True,
            )
        except Exception as exc:  # noqa: BLE001
            return ToolResult(output=str(exc), is_error=True)

    return definition, execute
