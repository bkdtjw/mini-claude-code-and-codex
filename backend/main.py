import os
import sys

import uvicorn

if getattr(sys, "frozen", False):
    os.chdir(os.path.dirname(sys.executable))

from backend.api.app import create_app
from backend.config.settings import settings

app = create_app()


if __name__ == "__main__":
    uvicorn.run(app, host=settings.api_host, port=settings.api_port, reload=not getattr(sys, "frozen", False))
