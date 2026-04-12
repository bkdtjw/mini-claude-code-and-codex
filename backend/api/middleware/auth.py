from __future__ import annotations

import secrets
from typing import Final

from fastapi import Header, HTTPException

from backend.common.errors import AgentError
from backend.config.settings import settings

AUTH_CONFIG_MESSAGE: Final[str] = "Authentication secret is not configured"
UNAUTHORIZED_DETAIL: Final[dict[str, str]] = {
    "code": "UNAUTHORIZED",
    "message": "Invalid or missing authentication token",
}
BEARER_PREFIX: Final[str] = "Bearer "


class AuthError(AgentError):
    """Authentication failure."""


def _build_http_error(code: str, message: str, status_code: int) -> HTTPException:
    return HTTPException(status_code=status_code, detail={"code": code, "message": message})


def _extract_bearer_token(authorization: str) -> str:
    value = authorization.strip()
    if not value.startswith(BEARER_PREFIX):
        return ""
    return value[len(BEARER_PREFIX) :].strip()


async def verify_token(authorization: str = Header(default="")) -> None:
    try:
        expected_token = settings.auth_secret.strip()
        if not expected_token:
            raise AuthError("AUTH_CONFIG_ERROR", AUTH_CONFIG_MESSAGE)
        provided_token = _extract_bearer_token(authorization)
        if not provided_token or not secrets.compare_digest(provided_token, expected_token):
            raise AuthError(
                UNAUTHORIZED_DETAIL["code"],
                UNAUTHORIZED_DETAIL["message"],
            )
    except AuthError as exc:
        if exc.code == "AUTH_CONFIG_ERROR":
            raise _build_http_error(exc.code, exc.message, 500) from exc
        raise _build_http_error(
            UNAUTHORIZED_DETAIL["code"],
            UNAUTHORIZED_DETAIL["message"],
            401,
        ) from exc
    except Exception as exc:
        raise _build_http_error(
            UNAUTHORIZED_DETAIL["code"],
            UNAUTHORIZED_DETAIL["message"],
            401,
        ) from exc


__all__ = ["AuthError", "verify_token"]
