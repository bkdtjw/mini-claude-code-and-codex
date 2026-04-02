# Agent Studio

自建 AI Coding Agent 平台 — Web 界面 + OpenAI 兼容 API + 完整 Agent 引擎。

## 架构总览

```
┌─────────────────────────────────────────────────────────────┐
│                  frontend/ (React + Vite)                    │
│  Dashboard │ Chat │ Diff │ Terminal │ TaskBoard │ TeamView  │
└──────────────────────────┬──────────────────────────────────┘
                           │ WebSocket + REST
┌──────────────────────────▼──────────────────────────────────┐
│              backend/api/ (FastAPI)                          │
│  POST /v1/chat/completions (OpenAI 兼容)                    │
│  /sessions │ /agents │ /tasks │ /teams │ /ws                │
└──────────────────────────┬──────────────────────────────────┘
                           │
┌──────────────────────────▼──────────────────────────────────┐
│  backend/adapters/       │  backend/core/ (Agent 引擎)      │
│  Anthropic│OpenAI│Ollama │  s01 Loop → s02 Tools → s03 Todo │
│                          │  s04 SubAgent  s05 Skills        │
│                          │  s06 Compress  s07 Tasks         │
│                          │  s08 Background s09 Teams        │
│                          │  s10 Protocol  s11 Autonomous    │
│                          │  s12 Worktree Isolation          │
└──────────────────────────┬──────────────────────────────────┘
                           │
┌──────────────────────────▼──────────────────────────────────┐
│              backend/storage/                                │
│  SQLite/Postgres │ FileStore │ SessionStore │ VectorStore    │
└─────────────────────────────────────────────────────────────┘
```

## 技术栈

- **后端**: Python 3.12+ / FastAPI / Pydantic v2 / httpx / SQLAlchemy
- **前端**: React 19 / Vite / Tailwind / Zustand / Monaco Editor
- **通信**: WebSocket (实时流) + SSE (OpenAI streaming 兼容)
- **存储**: SQLite (开发) / PostgreSQL (生产)

## 快速开始

```bash
make install     # 安装依赖
make dev-api     # 启动后端 http://localhost:8000
make dev-web     # 启动前端 http://localhost:3000
make test        # 运行测试
```

## OpenAI 兼容接口

```bash
curl http://localhost:8000/v1/chat/completions \
  -H "Authorization: Bearer your-key" \
  -d '{"model":"claude-sonnet-4-20250514","messages":[{"role":"user","content":"读一下 main.py"}],"stream":true}'
```

## SubAgent 能力

- 已支持 `dispatch_agent` 子 Agent 派生。
- 已支持并行子任务：传入 `tasks`（数组）和可选 `max_concurrent`（默认 3）即可并发执行。
