"""Feishu Open API client for bidirectional communication."""
from __future__ import annotations

import json
import logging
import time
from typing import Any

import httpx

from backend.common.feishu_markdown import strip_markdown_for_feishu

logger = logging.getLogger(__name__)

_TOKEN_URL = "https://open.feishu.cn/open-apis/auth/v3/tenant_access_token/internal/"
_SEND_MSG_URL = "https://open.feishu.cn/open-apis/im/v1/messages"
_TOKEN_TTL_MARGIN = 300  # refresh 5 min before expiry


class FeishuClient:
    """Wraps Feishu Open Platform APIs: token management, send, reply."""

    def __init__(self, app_id: str, app_secret: str) -> None:
        self._app_id = app_id
        self._app_secret = app_secret
        self._token: str = ""
        self._token_expires: float = 0.0

    async def _ensure_token(self) -> None:
        if self._token and time.time() < self._token_expires - _TOKEN_TTL_MARGIN:
            return
        try:
            async with httpx.AsyncClient(timeout=10.0, trust_env=False) as client:
                resp = await client.post(
                    _TOKEN_URL,
                    json={
                        "app_id": self._app_id,
                        "app_secret": self._app_secret,
                    },
                )
                data = resp.json()
        except Exception:
            logger.exception("Failed to get feishu tenant_access_token")
            return
        if data.get("code") != 0:
            logger.error("Feishu token error: %s", data.get("msg"))
            return
        self._token = data["tenant_access_token"]
        self._token_expires = time.time() + data.get("expire", 7200)

    def _headers(self) -> dict[str, str]:
        return {"Authorization": f"Bearer {self._token}"}

    def _build_content(self, content: str, msg_type: str) -> str:
        """Strip markdown from text/post content. Interactive passes through."""
        if msg_type not in ("text", "post"):
            return content
        try:
            data = json.loads(content)
        except (json.JSONDecodeError, TypeError):
            return content
        if msg_type == "text":
            text = data.get("text", "")
            if text:
                data["text"] = strip_markdown_for_feishu(text)
        elif msg_type == "post":
            for lang_data in data.get("post", {}).values():
                for paragraph in lang_data.get("content", []):
                    for element in paragraph:
                        if element.get("tag") == "text":
                            element["text"] = strip_markdown_for_feishu(
                                element.get("text", ""),
                            )
        return json.dumps(data, ensure_ascii=False)

    async def send_message(
        self,
        chat_id: str,
        content: str,
        msg_type: str = "text",
    ) -> dict[str, Any]:
        await self._ensure_token()
        content = self._build_content(content, msg_type)
        body: dict[str, Any] = {
            "receive_id": chat_id,
            "msg_type": msg_type,
            "content": content,
        }
        async with httpx.AsyncClient(timeout=10.0, trust_env=False) as client:
            resp = await client.post(
                _SEND_MSG_URL,
                headers=self._headers(),
                params={"receive_id_type": "chat_id"},
                json=body,
            )
            return resp.json()

    async def reply_message(
        self,
        message_id: str,
        content: str,
        msg_type: str = "text",
    ) -> dict[str, Any]:
        await self._ensure_token()
        content = self._build_content(content, msg_type)
        url = f"{_SEND_MSG_URL}/{message_id}/reply"
        body: dict[str, Any] = {"msg_type": msg_type, "content": content}
        async with httpx.AsyncClient(timeout=10.0, trust_env=False) as client:
            resp = await client.post(url, headers=self._headers(), json=body)
            return resp.json()


__all__ = ["FeishuClient"]
