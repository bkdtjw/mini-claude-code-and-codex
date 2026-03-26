import uvicorn

from backend.api.app import create_app
from backend.config.settings import settings

app = create_app()


if __name__ == "__main__":
    uvicorn.run("backend.main:app", host=settings.api_host, port=settings.api_port, reload=True)
