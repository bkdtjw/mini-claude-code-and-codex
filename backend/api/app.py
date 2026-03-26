"""FastAPI application factory."""
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware


def create_app() -> FastAPI:
    from backend.api.routes import chat_completions, providers, sessions, websocket

    app = FastAPI(title="Agent Studio", version="0.1.0")
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

    @app.get("/health")
    async def health():
        return {"status": "ok"}

    return app
