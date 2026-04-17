"""FastAPI application factory."""
from __future__ import annotations

import logging
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from backend.common.errors import AgentError
from backend.config import close_redis, init_redis, settings as app_settings
from backend.storage import SessionStore, init_db

logger = logging.getLogger(__name__)


@asynccontextmanager
async def _lifespan(app: FastAPI) -> AsyncIterator[None]:
    from backend.api.routes.mcp import mcp_server_manager

    task_scheduler = None
    try:
        await init_db()
        await init_redis()
        app.state.session_store = SessionStore()
        try:
            from backend.adapters.provider_manager import ProviderManager
            from backend.core.s02_tools.mcp import MCPServerManager
            from backend.core.s07_task_system.executor import TaskExecutor
            from backend.core.s07_task_system.scheduler import TaskScheduler
            from backend.core.s07_task_system.store import TaskStore

            store = TaskStore()
            # Create FeishuClient if app credentials are configured
            feishu_client = None
            if app_settings.feishu_app_id and app_settings.feishu_app_secret:
                from backend.core.s02_tools.builtin.feishu_client import FeishuClient
                feishu_client = FeishuClient(
                    app_id=app_settings.feishu_app_id,
                    app_secret=app_settings.feishu_app_secret,
                )
            executor = TaskExecutor(ProviderManager(), MCPServerManager(), feishu_client)
            task_scheduler = TaskScheduler(store, executor)
            # Expose executor for card action handlers (rerun button)
            try:
                from backend.api.routes.feishu_card_action import set_task_executor
                set_task_executor(executor)
            except Exception:  # noqa: BLE001
                pass
            await task_scheduler.start()
        except Exception:  # noqa: BLE001
            logger.exception("Failed to start TaskScheduler")
        try:
            _init_feishu_handler()
        except Exception:  # noqa: BLE001
            logger.exception("Failed to init Feishu handler")
        yield
    except Exception as exc:  # noqa: BLE001
        raise AgentError("APP_LIFESPAN_ERROR", str(exc)) from exc
    finally:
        if task_scheduler is not None:
            try:
                await task_scheduler.stop()
            except Exception:  # noqa: BLE001
                pass
        await close_redis()
        try:
            await mcp_server_manager.disconnect_all()
        except Exception as exc:  # noqa: BLE001
            raise AgentError("APP_SHUTDOWN_ERROR", str(exc)) from exc


def _init_feishu_handler() -> None:
    if not app_settings.feishu_app_id or not app_settings.feishu_app_secret:
        return
    from backend.adapters.provider_manager import ProviderManager
    from backend.api.routes.feishu import set_handler
    from backend.api.routes.feishu_handler import FeishuMessageHandler
    from backend.core.s02_tools.builtin.feishu_client import FeishuClient

    client = FeishuClient(
        app_id=app_settings.feishu_app_id,
        app_secret=app_settings.feishu_app_secret,
    )
    handler = FeishuMessageHandler(client, ProviderManager())
    set_handler(handler)
    logger.info("Feishu bidirectional handler initialized")


def create_app() -> FastAPI:
    from backend.api.routes import chat_completions, mcp, providers, sessions, websocket
    from backend.api.routes.reports import router as reports_router

    app = FastAPI(title="Agent Studio", version="0.1.0", lifespan=_lifespan)
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )
    app.include_router(chat_completions.router)
    app.include_router(websocket.router)
    app.include_router(sessions.router)
    app.include_router(providers.router)
    app.include_router(mcp.router)
    app.include_router(reports_router)

    if app_settings.feishu_app_id and app_settings.feishu_app_secret:
        from backend.api.routes import feishu, feishu_card_action
        app.include_router(feishu.router)
        app.include_router(feishu_card_action.router)

    @app.get("/health")
    async def health() -> dict[str, str]:
        try:
            return {"status": "ok"}
        except Exception as exc:  # noqa: BLE001
            raise AgentError("HEALTHCHECK_ERROR", str(exc)) from exc

    return app
