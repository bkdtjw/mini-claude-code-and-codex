from __future__ import annotations

from time import monotonic

from backend.common.logging import get_logger
from backend.config import get_redis

logger = get_logger(component="feishu_menu_state")

_MODE_TTL_SECONDS = 7 * 24 * 3600
_CURRENT_KB_TTL_SECONDS = 7 * 24 * 3600
_PENDING_TTL_SECONDS = 5 * 60
_CHAT_TTL_SECONDS = 30 * 24 * 3600


class FeishuMenuState:
    def __init__(self) -> None:
        self._user_modes: dict[str, str] = {}
        self._user_chats: dict[str, str] = {}
        self._current_kbs: dict[str, str] = {}
        self._pending_intents: dict[str, str] = {}
        self._pending_expires_at: dict[str, float] = {}

    async def set_mode(self, open_id: str, mode: str) -> None:
        self._user_modes[open_id] = mode
        redis = get_redis()
        if redis is None:
            return
        try:
            await redis.set(self._mode_key(open_id), mode, ex=_MODE_TTL_SECONDS)
        except Exception as exc:
            logger.warning("feishu_menu_state_set_mode_failed", open_id=open_id, error=str(exc))

    async def clear_mode(self, open_id: str) -> None:
        self._user_modes.pop(open_id, None)
        redis = get_redis()
        if redis is None:
            return
        try:
            await redis.delete(self._mode_key(open_id))
        except Exception as exc:
            logger.warning("feishu_menu_state_clear_mode_failed", open_id=open_id, error=str(exc))

    async def get_mode(self, open_id: str) -> str:
        redis = get_redis()
        if redis is not None:
            try:
                value = await redis.get(self._mode_key(open_id))
                if isinstance(value, str):
                    self._user_modes[open_id] = value
                    return value
            except Exception as exc:
                logger.warning("feishu_menu_state_get_mode_failed", open_id=open_id, error=str(exc))
        return self._user_modes.get(open_id, "")

    async def set_current_kb(self, open_id: str, kb_id: str) -> None:
        self._current_kbs[open_id] = kb_id
        await self._set_value(self._kb_key(open_id), kb_id, _CURRENT_KB_TTL_SECONDS)

    async def get_current_kb(self, open_id: str) -> str:
        value = await self._get_value(self._kb_key(open_id))
        if value:
            self._current_kbs[open_id] = value
            return value
        return self._current_kbs.get(open_id, "")

    async def set_pending(self, open_id: str, intent: str) -> None:
        self._pending_intents[open_id] = intent
        self._pending_expires_at[open_id] = monotonic() + _PENDING_TTL_SECONDS
        await self._set_value(self._pending_key(open_id), intent, _PENDING_TTL_SECONDS)

    async def get_pending(self, open_id: str) -> str:
        value = await self._get_value(self._pending_key(open_id))
        if value:
            self._pending_intents[open_id] = value
            self._pending_expires_at[open_id] = monotonic() + _PENDING_TTL_SECONDS
            return value
        if get_redis() is not None:
            self._pending_intents.pop(open_id, None)
            self._pending_expires_at.pop(open_id, None)
            return ""
        if self._pending_expires_at.get(open_id, 0) > monotonic():
            return self._pending_intents.get(open_id, "")
        self._pending_intents.pop(open_id, None)
        self._pending_expires_at.pop(open_id, None)
        return ""

    async def clear_pending(self, open_id: str) -> None:
        self._pending_intents.pop(open_id, None)
        self._pending_expires_at.pop(open_id, None)
        redis = get_redis()
        if redis is None:
            return
        try:
            await redis.delete(self._pending_key(open_id))
        except Exception as exc:
            logger.warning(
                "feishu_menu_state_clear_pending_failed",
                open_id=open_id,
                error=str(exc),
            )

    async def set_chat(self, open_id: str, chat_id: str) -> None:
        self._user_chats[open_id] = chat_id
        redis = get_redis()
        if redis is None:
            return
        try:
            await redis.set(self._chat_key(open_id), chat_id, ex=_CHAT_TTL_SECONDS)
        except Exception as exc:
            logger.warning("feishu_menu_state_set_chat_failed", open_id=open_id, error=str(exc))

    async def get_chat(self, open_id: str) -> str:
        redis = get_redis()
        if redis is not None:
            try:
                value = await redis.get(self._chat_key(open_id))
                if isinstance(value, str):
                    self._user_chats[open_id] = value
                    return value
            except Exception as exc:
                logger.warning("feishu_menu_state_get_chat_failed", open_id=open_id, error=str(exc))
        return self._user_chats.get(open_id, "")

    async def _set_value(self, key: str, value: str, ttl_seconds: int) -> None:
        redis = get_redis()
        if redis is None:
            return
        try:
            await redis.set(key, value, ex=ttl_seconds)
        except Exception as exc:
            logger.warning("feishu_menu_state_set_value_failed", key=key, error=str(exc))

    async def _get_value(self, key: str) -> str:
        redis = get_redis()
        if redis is None:
            return ""
        try:
            value = await redis.get(key)
            return value if isinstance(value, str) else ""
        except Exception as exc:
            logger.warning("feishu_menu_state_get_value_failed", key=key, error=str(exc))
            return ""

    @staticmethod
    def _mode_key(open_id: str) -> str:
        return f"feishu:user_mode:{open_id}"

    @staticmethod
    def _chat_key(open_id: str) -> str:
        return f"feishu:user_chat:{open_id}"

    @staticmethod
    def _kb_key(open_id: str) -> str:
        return f"feishu:current_kb:{open_id}"

    @staticmethod
    def _pending_key(open_id: str) -> str:
        return f"feishu:pending:{open_id}"


__all__ = ["FeishuMenuState"]
