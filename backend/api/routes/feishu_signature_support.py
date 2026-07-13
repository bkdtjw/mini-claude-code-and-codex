"""Shared Feishu callback signature verification for route modules.

Reads the real Lark request headers and delegates to
``backend.common.feishu_signature.verify_signature`` so the main event route and
the card action route share the same (correct) verification as ``feishu_events``.
"""

from __future__ import annotations

import json

from fastapi import Request

from backend.common.errors import AgentError
from backend.common.feishu_signature import verify_signature
from backend.common.logging import get_logger
from backend.config.settings import settings

logger = get_logger(component="feishu_signature_support")


def request_signature_ok(request: Request, body: bytes) -> bool:
    """Return True when the callback passes Feishu's official verification.

    Reads the real Lark headers ``X-Lark-Request-Timestamp`` /
    ``X-Lark-Request-Nonce`` / ``X-Lark-Signature``. 加密模式（配了
    ``feishu_encrypt_key``）按签名头校验；明文模式（只配
    ``feishu_verification_token``）飞书不发签名头，改为比对 body 内的 token
    字段；两者都未配置（dev 默认）放行。校验不过或内部错误返回 False，
    由调用方拒绝请求。
    """
    timestamp = request.headers.get("X-Lark-Request-Timestamp", "")
    nonce = request.headers.get("X-Lark-Request-Nonce", "")
    signature = request.headers.get("X-Lark-Signature", "")
    try:
        ok = verify_signature(
            body,
            timestamp,
            nonce,
            signature,
            str(getattr(settings, "feishu_verification_token", "") or ""),
            str(getattr(settings, "feishu_encrypt_key", "") or ""),
        )
    except AgentError:
        logger.warning("feishu_signature_verify_error")
        return False
    if not ok:
        _log_reject_shape(signature, body)
    return ok


def _log_reject_shape(signature: str, body: bytes) -> None:
    """拒绝时输出请求形态诊断（token 只落前 4 位），区分三类故障：
    加密模式未配 encrypt_key / 后台 token 与 env 不一致 / body 无 token 字段。"""
    body_is_encrypt = False
    token_head = ""
    has_token_field = False
    try:
        data = json.loads(body)
        if isinstance(data, dict):
            body_is_encrypt = "encrypt" in data
            token = ""
            header = data.get("header")
            if isinstance(header, dict):
                token = str(header.get("token") or "")
            if not token:
                token = str(data.get("token") or "")
            has_token_field = bool(token)
            token_head = token[:4]
    except Exception:  # noqa: BLE001
        pass
    expected = str(getattr(settings, "feishu_verification_token", "") or "")
    logger.warning(
        "feishu_signature_reject_shape",
        has_signature_header=bool(signature),
        body_is_encrypt=body_is_encrypt,
        has_token_field=has_token_field,
        body_token_head=token_head,
        expected_token_head=expected[:4],
        encrypt_key_configured=bool(getattr(settings, "feishu_encrypt_key", "") or ""),
    )


__all__ = ["request_signature_ok"]
