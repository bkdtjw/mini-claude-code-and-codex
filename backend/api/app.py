"""FastAPI application factory."""
from __future__ import annotations

import os
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles

from backend.common.errors import AgentError
from backend.common.logging import get_logger, setup_logging
from backend.common.metrics import close_metrics, init_metrics
from backend.config import close_redis, init_redis
from backend.config import settings as app_settings
from backend.core import init_agent_runtime
from backend.storage import SessionStore, init_db

from .lifespan_support import check_readiness, init_task_queue

logger = get_logger(component="api_app")
_FRONTEND_DIR = Path(os.getenv("FRONTEND_DIST_DIR", "/app/dist/frontend"))
_RESERVED_FRONTEND_PATHS = {"api", "assets", "health", "metrics", "reports", "v1", "ws"}


@asynccontextmanager
async def _lifespan(app: FastAPI) -> AsyncIterator[None]:
    from backend.api.routes.mcp import mcp_server_manager
    from backend.api.routes.providers import provider_manager

    task_scheduler = None
    try:
        await init_db()
        await init_redis()
        await init_metrics()
        app.state.session_store = SessionStore()
        spec_registry, agent_runtime = await init_agent_runtime(
            provider_manager=provider_manager,
            mcp_manager=mcp_server_manager,
            settings=app_settings,
        )
        app.state.spec_registry = spec_registry
        app.state.agent_runtime = agent_runtime
        init_task_queue(app)
        try:
            from backend.adapters.provider_manager import ProviderManager
            from backend.core.s02_tools.mcp import MCPServerManager
            from backend.core.s07_task_system import (
                TaskExecutor,
                TaskExecutorDeps,
                TaskScheduler,
                TaskStore,
            )

            store = TaskStore()
            # Create FeishuClient if app credentials are configured
            feishu_client = None
            if app_settings.feishu_app_id and app_settings.feishu_app_secret:
                from backend.core.s02_tools.builtin.feishu_client import FeishuClient
                feishu_client = FeishuClient(
                    app_id=app_settings.feishu_app_id,
                    app_secret=app_settings.feishu_app_secret,
                )
            executor = TaskExecutor(
                TaskExecutorDeps(
                    provider_manager=ProviderManager(),
                    mcp_manager=MCPServerManager(),
                    agent_runtime=getattr(app.state, "agent_runtime", None),
                    task_queue=getattr(app.state, "task_queue", None),
                    feishu_client=feishu_client,
                )
            )
            task_scheduler = TaskScheduler(store, executor)
            # Expose executor for card action handlers (rerun button)
            try:
                from backend.api.routes.feishu_card_action import set_task_executor
                set_task_executor(executor)
            except Exception:  # noqa: BLE001
                pass
            await task_scheduler.start()
        except Exception:  # noqa: BLE001
            logger.exception("task_scheduler_start_failed")
        try:
            _init_feishu_handler(app)
        except Exception:  # noqa: BLE001
            logger.exception("feishu_handler_init_failed")
        yield
    except Exception as exc:  # noqa: BLE001
        raise AgentError("APP_LIFESPAN_ERROR", str(exc)) from exc
    finally:
        if task_scheduler is not None:
            try:
                await task_scheduler.stop()
            except Exception:  # noqa: BLE001
                pass
        close_metrics()
        await close_redis()
        try:
            await mcp_server_manager.disconnect_all()
        except Exception as exc:  # noqa: BLE001
            raise AgentError("APP_SHUTDOWN_ERROR", str(exc)) from exc


def _init_feishu_handler(app: FastAPI) -> None:
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
    handler.configure_runtime(
        getattr(app.state, "agent_runtime", None),
        getattr(app.state, "spec_registry", None),
        getattr(app.state, "task_queue", None),
    )
    set_handler(handler)
    logger.info("feishu_handler_initialized")


def create_app() -> FastAPI:
    setup_logging(os.getenv("LOG_LEVEL", "INFO"))
    from backend.api.routes import (
        chat_completions,
        logs,
        mcp,
        metrics,
        providers,
        sessions,
        websocket,
    )
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
    app.include_router(metrics.router)
    app.include_router(logs.router)
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

    @app.get("/health/live")
    async def health_live() -> dict[str, str]:
        try:
            return {"status": "alive"}
        except Exception as exc:  # noqa: BLE001
            raise AgentError("HEALTH_LIVE_ERROR", str(exc)) from exc

    @app.get("/health/ready")
    async def health_ready() -> JSONResponse:
        try:
            status = await check_readiness()
            payload = {"status": "ready" if all(status.values()) else "not_ready", **status}
            return JSONResponse(status_code=200 if all(status.values()) else 503, content=payload)
        except Exception as exc:  # noqa: BLE001
            raise AgentError("HEALTH_READY_ERROR", str(exc)) from exc

    _mount_frontend(app)
    return app


def _mount_frontend(app: FastAPI) -> None:
    index_path = _FRONTEND_DIR / "index.html"
    assets_dir = _FRONTEND_DIR / "assets"
    if not index_path.is_file() or not assets_dir.is_dir():
        logger.warning("frontend_dist_not_found", path=str(_FRONTEND_DIR))
        return

    app.mount("/assets", StaticFiles(directory=str(assets_dir)), name="frontend-assets")

    @app.get("/", include_in_schema=False)
    async def frontend_index() -> FileResponse:
        return FileResponse(index_path)

    @app.get("/{full_path:path}", include_in_schema=False)
    async def frontend_spa(full_path: str) -> FileResponse:
        root_segment = full_path.split("/", 1)[0]
        if root_segment in _RESERVED_FRONTEND_PATHS:
            raise HTTPException(status_code=404, detail="Not found")
        return FileResponse(index_path)
