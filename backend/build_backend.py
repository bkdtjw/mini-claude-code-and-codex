import os

import PyInstaller.__main__

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
MAIN_FILE = os.path.join(ROOT, "backend", "main.py")
HTTP_CLIENT_JSON = os.path.join(ROOT, "backend", "config", "http_client.json")
PROVIDERS_JSON = os.path.join(ROOT, "backend", "config", "providers.json")
MCP_SERVERS_JSON = os.path.join(ROOT, "backend", "config", "mcp_servers.json")
SCHEDULED_TASKS_JSON = os.path.join(ROOT, "backend", "config", "scheduled_tasks.json")
CONFIG_TARGET = os.path.join("backend", "config")

PyInstaller.__main__.run(
    [
        arg
        for arg in [
            MAIN_FILE,
            "--name=agent-studio-backend",
            "--onefile",
            "--console",
            "--clean",
            "--runtime-tmpdir=%TEMP%\\agent-studio-backend",
            "--distpath=dist/backend",
            "--workpath=build/backend",
            "--specpath=build",
            "--hidden-import=uvicorn.logging",
            "--hidden-import=uvicorn.protocols.http.auto",
            "--hidden-import=uvicorn.protocols.websockets.auto",
            "--hidden-import=uvicorn.lifespan.on",
            "--hidden-import=uvicorn.lifespan.off",
            "--hidden-import=backend.api",
            "--hidden-import=backend.api.routes",
            "--hidden-import=backend.api.routes.chat_completions",
            "--hidden-import=backend.api.routes.websocket",
            "--hidden-import=backend.api.routes.sessions",
            "--hidden-import=backend.api.routes.providers",
            "--hidden-import=backend.adapters",
            "--hidden-import=backend.core",
            "--hidden-import=backend.core.s01_agent_loop",
            "--hidden-import=backend.core.s02_tools",
            "--hidden-import=backend.core.s02_tools.builtin",
            "--hidden-import=backend.common",
            "--hidden-import=backend.common.types",
            "--hidden-import=backend.config",
            "--hidden-import=pydantic_settings",
            "--hidden-import=dotenv",
            f"--add-data={HTTP_CLIENT_JSON}{os.pathsep}{CONFIG_TARGET}",
            f"--add-data={PROVIDERS_JSON}{os.pathsep}{CONFIG_TARGET}" if os.path.exists(PROVIDERS_JSON) else "",
            f"--add-data={MCP_SERVERS_JSON}{os.pathsep}{CONFIG_TARGET}" if os.path.exists(MCP_SERVERS_JSON) else "",
            f"--add-data={SCHEDULED_TASKS_JSON}{os.pathsep}{CONFIG_TARGET}"
            if os.path.exists(SCHEDULED_TASKS_JSON)
            else "",
        ]
        if arg
    ]
)
