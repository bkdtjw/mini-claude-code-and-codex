"""Feishu event callback route for bidirectional communication."""
from __future__ import annotations

import asyncio
import hashlib
import hmac
import json
from typing import Any

from fastapi import APIRouter, Request

from backend.common.logging import bound_log_context, get_logger, new_trace_id
from backend.config.settings import settings as app_settings

logger = get_logger(component="feishu_route")

router = APIRouter(prefix="/api/feishu", tags=["feishu"])

_handler: Any = None


def set_handler(handler: Any) -> None:
    global _handler  # noqa: PLW0603
    _handler = handler


def _verify_signature(body: bytes, timestamp: str, signature: str) -> bool:
    token = app_settings.feishu_verification_token
    if not token:
        return True
    string_to_sign = f"{timestamp}\n{token}"
    expected = hmac.new(
        string_to_sign.encode("utf-8"),
        body,
        digestmod=hashlib.sha256,
    ).hexdigest()
    return hmac.compare_digest(expected, signature)


@router.post("/event")
async def feishu_event(request: Request) -> dict[str, Any]:
    body = await request.body()
    try:
        data = json.loads(body)
    except (json.JSONDecodeError, TypeError):
        return {"error": "invalid json"}

    # URL verification challenge
    if data.get("type") == "url_verification":
        return {"challenge": data.get("challenge", "")}

    event_id = data.get("header", {}).get("event_id", "")
    event_type = data.get("header", {}).get("event_type", "")
    chat_id = data.get("event", {}).get("message", {}).get("chat_id", "")

    # Signature verification
    timestamp = request.headers.get("X-Lark-Signature-Timestamp", "")
    signature = request.headers.get("X-Lark-Signature-Signature", "")
    if timestamp and signature:
        if not _verify_signature(body, timestamp, signature):
            logger.warning("feishu_signature_invalid")
            return {"error": "signature mismatch"}

    # Card action fallback: action field without header → card callback
    if data.get("action") and not data.get("header"):
        from backend.schemas.feishu import FeishuCardActionPayload

        from backend.api.routes.feishu_card_action import dispatcher

        try:
            payload = FeishuCardActionPayload.model_validate(data)
            return await dispatcher.dispatch(payload)
        except Exception:
            logger.warning("feishu_card_action_fallback_failed")
            return {}

    if event_type != "im.message.receive_v1":
        return {"status": "ignored"}

    with bound_log_context(trace_id=new_trace_id(), session_id=chat_id):
        logger.info("feishu_event_received", event_id=event_id, event_type=event_type)
        if _handler is not None:
            asyncio.create_task(_handler.handle_message(data))

    return {"status": "ok"}
