from __future__ import annotations

from typing import Any

from backend.common.logging import get_logger
from backend.config import settings
from backend.core.s07_task_system.event_hooks_runtime import build_hook_runtime
from backend.core.s07_task_system.event_hooks_runtime.scheduler import HookScheduler

logger = get_logger(component="event_hooks_startup")

_active: HookScheduler | None = None


async def start_event_hooks_engine(
    app: Any,
    provider_manager: Any,
) -> HookScheduler | None:
    global _active
    try:
        if _active is not None:
            return _active
        providers = await provider_manager.list_all()
        if not providers:
            logger.warning("event_hooks_engine_no_provider")
            return None
        default = next((provider for provider in providers if provider.is_default), providers[0])
        adapter = await provider_manager.get_adapter(default.id)
        runtime = build_hook_runtime(adapter, settings.default_model)
        app.state.hook_runtime = runtime
        scheduler = HookScheduler(app.state.hook_store, runtime)
        await scheduler.start()
        _active = scheduler
        return scheduler
    except Exception as exc:  # noqa: BLE001
        logger.exception("event_hooks_engine_start_failed", error=str(exc))
        return None


async def stop_event_hooks_engine() -> None:
    global _active
    try:
        if _active is None:
            return
        await _active.stop()
    except Exception as exc:  # noqa: BLE001
        logger.exception("event_hooks_engine_stop_failed", error=str(exc))
    finally:
        _active = None


__all__ = ["start_event_hooks_engine", "stop_event_hooks_engine"]
