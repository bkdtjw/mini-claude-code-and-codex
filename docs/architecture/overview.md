# 架构概述

## 目录结构

```
agent-studio/
├── backend/                    # Python 后端
│   ├── main.py                 # uvicorn 入口
│   ├── config.py               # Pydantic Settings
│   ├── api/                    # FastAPI 路由层 (唯一 HTTP 入口)
│   │   ├── routes/             # 路由: chat_completions, sessions, websocket...
│   │   └── middleware/         # 认证, 限流, 错误处理, OpenAI 格式转换
│   ├── adapters/               # LLM 适配器 (Anthropic, OpenAI, Ollama)
│   ├── common/                 # 公共类型 (Pydantic models), 错误, 工具
│   │   └── types/              # message.py, tool.py, agent.py, llm.py...
│   ├── core/                   # Agent 引擎 (纯 Python, 不依赖 FastAPI)
│   │   ├── s01_agent_loop/     # 主循环 + 状态机 + 消息队列
│   │   ├── s02_tools/          # 工具注册 + 执行 + 沙箱 + MCP + 内置工具
│   │   ├── s03_todo_write/     # 任务规划 + 里程碑 + 检查点
│   │   ├── s04_sub_agents/     # 子Agent生成 + 池化 + 父子通信
│   │   ├── s05_skills/         # 技能按需加载 + 注册 + 模板
│   │   ├── s06_context_compression/  # 上下文压缩 + 摘要 + 长期记忆
│   │   ├── s07_task_system/    # 任务队列 + 依赖图 + 调度
│   │   ├── s08_background_tasks/    # Worker 池 + 事件总线
│   │   ├── s09_agent_teams/    # 团队管理 + 角色 + 协调
│   │   ├── s10_team_protocol/  # 邮箱 + 消息总线 + 契约
│   │   ├── s11_autonomous_agent/    # 目标引擎 + 自监控
│   │   ├── s12_worktree_isolation/  # git worktree + 沙箱
│   │   └── permissions/        # 权限规则 + 审批流
│   └── storage/                # 数据库 + 文件 + 会话 + 向量存储
├── frontend/                   # React + Vite 前端
├── skills/                     # 技能定义 (Markdown + JSON)
├── agents/                     # Agent 角色定义 (Markdown)
├── tests/                      # pytest 测试
├── config/                     # TOML 配置文件
├── deploy/                     # Docker + K8s
└── docs/                       # 文档
```

## 关键设计原则

1. core/ 与 api/ 完全解耦: core 是纯 asyncio 代码，可以脱离 FastAPI 单独使用
2. 适配器模式: LLM 调用通过抽象基类 LLMAdapter 注入，切换 provider 零改动
3. Pydantic 贯穿全栈: 类型定义、请求验证、序列化、配置管理全用 Pydantic v2
