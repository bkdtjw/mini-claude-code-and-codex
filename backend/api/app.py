"""FastAPI application factory."""
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware


def create_app() -> FastAPI:
    from backend.api.routes.providers import router as providers_router

    app = FastAPI(title="Agent Studio", version="0.1.0")
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )
    app.include_router(providers_router)

    @app.get("/health")
    async def health():
        return {"status": "ok"}

    return app
