# Agent Studio vs DeerFlow 详细对比报告

## 1. 项目定位与目标用户

### Agent Studio
- **定位**: 模块化的 Agent 开发框架和运行时环境
- **目标用户**: 需要构建自定义 Agent 系统的开发者
- **核心目标**: 提供一个可扩展的 Agent 基础设施，支持多 Agent 协作、工具系统、团队协议等
- **设计理念**: 强调模块化架构，每个模块 (s01-s12) 负责特定功能，通过 `__init__.py` 暴露接口

### DeerFlow
- **定位**: "Super Agent Harness" - 开箱即用的超级 Agent 运行时
- **目标用户**: 终端用户和需要快速部署 Agent 系统的开发者
- **核心目标**: 提供一个完整的 Deep Research 和任务执行系统，具备沙箱、记忆、子 Agent 等完整能力
- **设计理念**: "Batteries included" - 包含所有必要组件，可直接使用

---

## 2. 技术栈对比

| 维度 | Agent Studio | DeerFlow |
|------|-------------|----------|
| **后端语言** | Python 3.12+ | Python 3.12+ |
| **Web 框架** | FastAPI | FastAPI (Gateway) + LangGraph Server |
| **Pydantic** | v2 | v2 |
| **前端** | React 19 + Vite | Next.js (App Router) |
| **前端状态管理** | Zustand | React Context + Hooks |
| **数据库** | SQLite (aiosqlite) / PostgreSQL | SQLite (LangGraph checkpointer) |
| **Agent 框架** | 自定义实现 | LangGraph + LangChain |
| **流式通信** | WebSocket + SSE | SSE (LangGraph 协议) |
| **进程管理** | asyncio | asyncio + ThreadPool |
| **包管理** | setuptools | uv (现代 Python 包管理器) |
| **容器化** | Docker Compose | Docker Compose + Nginx |

### 关键差异

**Agent Studio**:
- 使用自定义 Agent Loop 实现，不依赖 LangGraph
- WebSocket 作为实时通信主要方式
- React + Vite 轻量级前端

**DeerFlow**:
- 深度集成 LangGraph 和 LangChain
- 使用 LangGraph 的 SSE 流协议
- Next.js 全功能前端

---

## 3. 架构设计

### Agent Studio 架构

```
agent-studio/
├── backend/
│   ├── core/                 # 纯 Python + asyncio，不依赖 FastAPI
│   │   ├── s01_agent_loop/   # Agent 执行循环
│   │   ├── s02_tools/        # 工具注册和执行
│   │   ├── s03_todo_write/   # 任务规划
│   │   ├── s04_sub_agents/   # 子 Agent 管理
│   │   ├── s05_skills/       # 技能系统
│   │   ├── s06_context_compression/  # 上下文压缩
│   │   ├── s07_task_system/  # 任务队列
│   │   ├── s08_background_tasks/     # 后台任务
│   │   ├── s09_agent_teams/  # Agent 团队
│   │   ├── s10_team_protocol/# 团队通信协议
│   │   ├── s11_autonomous_agent/     # 自主 Agent
│   │   └── s12_worktree_isolation/   # Git worktree 隔离
│   ├── api/                  # 唯一 HTTP 入口 (FastAPI)
│   ├── adapters/             # LLM 适配器层
│   ├── storage/              # 数据持久化
│   └── common/types/         # Pydantic 类型定义
├── frontend/                 # React 前端
├── agents/                   # Agent 角色定义
└── skills/                   # 技能定义
```

### DeerFlow 架构

```
deer-flow/
├── backend/
│   ├── packages/harness/     # 可发布包 (deerflow-harness)
│   │   └── deerflow/
│   │       ├── agents/       # LangGraph Agent
│   │       │   ├── lead_agent/      # 主 Agent
│   │       │   ├── middlewares/     # 14 个中间件
│   │       │   └── memory/          # 记忆系统
│   │       ├── sandbox/      # 沙箱系统
│   │       ├── subagents/    # 子 Agent 系统
│   │       ├── tools/        # 工具系统
│   │       ├── mcp/          # MCP 集成
│   │       ├── models/       # LLM 工厂
│   │       ├── skills/       # 技能系统
│   │       ├── config/       # 配置系统
│   │       ├── community/    # 社区工具 (search, sandbox)
│   │       └── client.py     # 嵌入式客户端
│   ├── app/                  # 应用层 (不可发布)
│   │   ├── gateway/          # FastAPI Gateway
│   │   └── channels/         # IM 渠道集成
│   └── tests/
├── frontend/                 # Next.js 前端
└── skills/                   # 技能定义
```

### 架构哲学对比

| 特性 | Agent Studio | DeerFlow |
|------|-------------|----------|
| **分层边界** | `core/` 不依赖 FastAPI，`api/` 是唯一 HTTP 层 | `harness/` (可发布) vs `app/` (不可发布)，严格单向依赖 |
| **模块通信** | 只通过 `__init__.py` 暴露的接口 | LangGraph 状态传递 + 函数调用 |
| **扩展机制** | 模块化替换 | Middleware 链 + 配置驱动 |
| **框架依赖** | 最小化框架依赖 | 深度依赖 LangGraph/LangChain |

---

## 4. Agent 执行模型

### Agent Studio

**核心文件**: `backend/core/s01_agent_loop/agent_loop.py`

**实现方式**:
```python
class AgentLoop:
    def __init__(self):
        self.state = AgentState.IDLE
        self.iteration_count = 0
        self.max_iterations = 50
    
    async def run(self, user_message: str) -> Message:
        # 1. 状态机驱动: idle -> thinking -> tool_calling -> done
        # 2. 事件驱动: on_status_change, on_message, on_tool_call
        # 3. 支持 abort() 中断执行
        # 4. 工具失败重试机制
```

**关键特性**:
- **状态机驱动**: `state_machine.py` 管理状态转换
- **事件系统**: `event_emitter.py` 实现发布订阅模式
- **迭代限制**: 默认最多 50 轮
- **钩子系统**: `hooks.py` 支持自定义钩子
- **可中断**: `abort()` 方法支持用户中断

### DeerFlow

**核心文件**: `backend/packages/harness/deerflow/agents/lead_agent/agent.py`

**实现方式**:
```python
def make_lead_agent(config: RunnableConfig):
    # 使用 langchain.agents.create_agent 创建
    agent = create_agent(
        model=model,
        tools=tools,
        state_schema=ThreadState,
        # 14 个 Middleware 链
    )
    return agent
```

**Middleware 链** (按执行顺序):
1. `ThreadDataMiddleware` - 线程数据初始化
2. `UploadsMiddleware` - 上传文件处理
3. `SandboxMiddleware` - 沙箱初始化
4. `DanglingToolCallMiddleware` - 修复悬空工具调用
5. `GuardrailMiddleware` - 安全护栏
6. `SummarizationMiddleware` - 对话摘要
7. `TodoListMiddleware` - 任务列表管理
8. `TitleMiddleware` - 自动生成标题
9. `MemoryMiddleware` - 记忆更新
10. `ViewImageMiddleware` - 图像查看
11. `SubagentLimitMiddleware` - Subagent 并发限制
12. `LoopDetectionMiddleware` - 循环检测
13. `ToolErrorHandlingMiddleware` - 工具错误处理
14. `ClarificationMiddleware` - 澄清请求拦截

### 对比总结

| 特性 | Agent Studio | DeerFlow |
|------|-------------|----------|
| **执行模型** | 自定义状态机 | LangGraph 状态图 |
| **扩展方式** | 钩子系统 | Middleware 链 |
| **中断机制** | `abort()` 方法 | LangGraph `Command(goto=END)` |
| **状态管理** | 自定义 `AgentState` | `ThreadState` (扩展 LangGraph) |
| **上下文管理** | 手动管理 + 压缩系统 | Middleware 自动处理 |

---

## 5. 工具系统

### Agent Studio

**核心文件**:
- `backend/core/s02_tools/registry.py` - 工具注册表
- `backend/core/s02_tools/executor.py` - 工具执行器
- `backend/core/s02_tools/security_gate.py` - 安全关卡

**实现方式**:
```python
class ToolRegistry:
    def register(
        self,
        name: str,
        definition: ToolDefinition,
        execute_fn: ToolExecuteFn
    ) -> None:
        # 注册工具定义和执行函数

class ToolExecutor:
    async def execute(self, call: ToolCall) -> ToolResult:
        # 执行单个工具调用
        # 输出截断: 最大 12000 字符
```

**内置工具**:
- `bash` - Bash 命令执行（带危险命令检测）
- `file_read` - 文件读取（带路径安全检查）
- `file_write` - 文件写入
- `dispatch_agent` - 子 Agent 派生
- `orchestrate_agents` - 多 Agent 编排

**安全机制**:
- `SecurityGate` - HMAC 签名验证
- 允许列表/危险工具列表
- 每轮最大调用次数限制

### DeerFlow

**核心文件**:
- `backend/packages/harness/deerflow/tools/tools.py` - 工具组装
- `backend/packages/harness/deerflow/sandbox/tools.py` - 沙箱工具

**内置工具**:
- `bash` - 执行命令
- `ls` - 目录列表
- `read_file` - 读取文件
- `write_file` - 写入文件
- `str_replace` - 字符串替换
- `present_files` - 向用户展示文件
- `ask_clarification` - 请求澄清
- `view_image` - 查看图像
- `task` - 委派给子 Agent

**工具来源** (按优先级):
1. Config-defined tools - `config.yaml` 中定义
2. MCP tools - 来自 MCP 服务器
3. Built-in tools - 内置工具
4. Subagent tool - 子 Agent 委派
5. Community tools - Tavily, Jina AI, Firecrawl 等

### MCP 支持对比

| 特性 | Agent Studio | DeerFlow |
|------|-------------|----------|
| **MCP 库** | 自定义实现 | `langchain-mcp-adapters` |
| **传输方式** | stdio, SSE | stdio, SSE, HTTP |
| **OAuth 支持** | 未知 | 完整支持 (client_credentials, refresh_token) |
| **缓存机制** | 未知 | mtime 检测自动失效 |
| **运行时更新** | 未知 | Gateway API 支持 |

### 对比总结

| 特性 | Agent Studio | DeerFlow |
|------|-------------|----------|
| **工具注册** | 程序化注册 | 配置驱动 + 程序化 |
| **安全验证** | HMAC 签名 | GuardrailMiddleware |
| **沙箱** | 基础路径检查 | 完整虚拟路径系统 + Docker |
| **工具来源** | 内置 + 自定义 | 内置 + MCP + Community + Subagent |

---

## 6. 多 Agent 协作

### Agent Studio

**核心文件**:
- `backend/core/s04_sub_agents/spawner.py` - 子 Agent 创建
- `backend/core/s04_sub_agents/orchestrator.py` - 多 Agent 编排
- `backend/core/s04_sub_agents/lifecycle.py` - 生命周期管理

**实现方式**:
```python
class SubAgentSpawner:
    def spawn(self, task: AgentTask) -> AgentLoop:
        # 创建新的 AgentLoop 实例
        # 过滤父级工具

class Orchestrator:
    async def execute_plan(self, plan: SimplePlan) -> list[SubAgentResult]:
        # 1. 解析阶段 (依赖解析)
        # 2. 并行执行同阶段任务
        # 3. 聚合结果
```

**关键特性**:
- **依赖解析**: `resolve_stages()` 解析任务依赖图
- **并行执行**: 同阶段任务并行
- **超时控制**: 默认 120 秒
- **权限控制**: `readonly` / `readwrite` 级别

### DeerFlow

**核心文件**:
- `backend/packages/harness/deerflow/subagents/executor.py`
- `backend/packages/harness/deerflow/subagents/builtins/general_purpose.py`

**实现方式**:
```python
class SubagentExecutor:
    MAX_CONCURRENT_SUBAGENTS = 3
    
    async def execute(self, task_request) -> SubagentResult:
        # 双线程池: _scheduler_pool + _execution_pool
        # 超时: 15 分钟
```

**Subagent 类型**:
- `general-purpose` - 通用子 Agent
- `bash` - Bash 命令专家

**并发控制**:
- 默认最大并发: 3
- `SubagentLimitMiddleware` 截断超额调用
- 15 分钟超时

### 对比总结

| 特性 | Agent Studio | DeerFlow |
|------|-------------|----------|
| **编排方式** | 依赖图 + 阶段执行 | 扁平化 + 并发限制 |
| **并发控制** | 依赖解析决定 | 固定限制 (3个) |
| **超时** | 120 秒 | 15 分钟 |
| **Agent 类型** | 自定义角色定义 | 内置类型 |
| **结果聚合** | 手动聚合 | 自动事件流 |

---

## 7. LLM 适配层

### Agent Studio

**核心文件**: `backend/adapters/`

**类结构**:
```python
class LLMAdapter(ABC):
    @abstractmethod
    async def test_connection(self) -> bool
    
    @abstractmethod
    async def complete(self, request: LLMRequest) -> LLMResponse
    
    @abstractmethod
    async def stream(self, request: LLMRequest) -> AsyncIterator[StreamChunk]
```

**适配器实现**:
- `AnthropicAdapter` - Claude API，支持 thinking blocks
- `OpenAICompatAdapter` - OpenAI/Kimi/GLM/DeepSeek 等
- `OllamaAdapter` - 本地模型

**特性**:
- 统一抽象基类
- 自动重试（3次）
- 流式响应支持

### DeerFlow

**核心文件**: `backend/packages/harness/deerflow/models/factory.py`

**实现方式**:
```python
def create_chat_model(name: str, thinking_enabled: bool = False):
    # 通过反射从 config.yaml 创建
    # 支持 thinking/vision/reasoning_effort
```

**支持的 Provider**:
- OpenAI (ChatOpenAI)
- Anthropic (Claude)
- DeepSeek
- MiniMax
- Codex CLI
- Claude Code OAuth

**特性**:
- 配置驱动创建
- 支持思考模式
- 支持视觉模型
- 支持推理强度设置

### 对比总结

| 特性 | Agent Studio | DeerFlow |
|------|-------------|----------|
| **设计模式** | 适配器模式 | 工厂模式 + 反射 |
| **配置方式** | JSON 文件持久化 | YAML 配置 |
| **支持的 Provider** | Anthropic, OpenAI, Ollama | OpenAI, Anthropic, DeepSeek, MiniMax, Codex, Claude Code |
| **扩展性** | 添加新 Adapter 类 | 配置即可 |
| **特殊功能** | 基础实现 | thinking/vision/reasoning 支持 |

---

## 8. 前端交互

### Agent Studio

**技术栈**:
- React 19
- Vite
- Tailwind CSS
- Zustand (状态管理)

**核心组件**:
- `App.tsx` - 主应用，React Router
- `pages/Session.tsx` - 会话页面
- `components/chat/` - ChatPanel, MessageList, InputBar, MessageBubble
- `components/sidebar/` - Sidebar, SessionList

**通信方式**:
- **WebSocket**: 主要实时通信 (`/ws/chat/{session_id}`)
- **SSE**: OpenAI 兼容接口 (`/v1/chat/completions`)

### DeerFlow

**技术栈**:
- Next.js (App Router)
- TypeScript
- Tailwind CSS
- LangGraph SDK

**核心目录**:
- `src/app/` - 页面路由
- `src/components/ai-elements/` - AI 组件
- `src/core/` - 核心逻辑
- `src/hooks/` - React Hooks

**通信方式**:
- **SSE**: LangGraph SSE 协议 (`values`, `messages-tuple`, `end`)
- **HTTP**: Gateway API

### 对比总结

| 特性 | Agent Studio | DeerFlow |
|------|-------------|----------|
| **框架** | React + Vite | Next.js |
| **状态管理** | Zustand | React Context + Hooks |
| **实时通信** | WebSocket | SSE |
| **协议** | 自定义 | LangGraph SSE 协议 |
| **流式处理** | WebSocket 消息 | SSE events |

---

## 9. 存储与持久化

### Agent Studio

**核心文件**: `backend/storage/`

**实现**:
```python
class SessionStore:
    # SQLAlchemy + aiosqlite
    async def create(self, session: Session) -> None
    async def get(self, session_id: str) -> Session | None
    async def save_messages(self, session_id: str, messages: list[Message]) -> None
```

**存储内容**:
- `SessionRecord` - 会话记录
- `MessageRecord` - 消息记录

### DeerFlow

**核心组件**:

1. **Checkpointer** (`agents/checkpointer/`):
   - SQLite 存储线程状态
   - 支持异步 provider

2. **Runtime Store** (`runtime/store/`):
   - JSON 文件存储
   - 线程状态映射

3. **Memory Storage** (`agents/memory/storage.py`):
   - 文件存储 (`memory.json`)
   - 结构化记忆数据

4. **Channel Store** (`app/channels/store.py`):
   - 渠道会话映射

### 对比总结

| 特性 | Agent Studio | DeerFlow |
|------|-------------|----------|
| **会话存储** | SQLAlchemy + SQLite | LangGraph Checkpointer |
| **消息存储** | 关系型数据库 | LangGraph 状态 |
| **记忆系统** | 无 | 完整长期记忆系统 |
| **配置存储** | JSON 文件 | YAML + JSON |

---

## 10. 部署方式

### Agent Studio

- **Docker Compose**: 基础配置
- **开发模式**: `uvicorn` 直接启动
- **生产模式**: 待完善

### DeerFlow

**部署选项**:
1. **Docker (推荐)**:
   ```bash
   make docker-init
   make docker-start
   ```

2. **本地开发**:
   ```bash
   make check
   make install
   make dev
   ```

3. **生产部署**:
   ```bash
   make up
   make down
   ```

**服务架构**:
- Nginx (port 2026) - 统一入口
- LangGraph Server (port 2024)
- Gateway API (port 8001)
- Frontend (port 3000)
- Provisioner (port 8002, optional)

### 对比总结

| 特性 | Agent Studio | DeerFlow |
|------|-------------|----------|
| **Docker** | 基础支持 | 完整支持 + 沙箱镜像 |
| **Nginx** | 未配置 | 内置配置 |
| **服务分离** | 单一服务 | 多服务架构 |
| **桌面端** | Electron 目录存在 | 不支持 |

---

## 11. 测试覆盖

### Agent Studio

- **框架**: pytest + pytest-asyncio
- **测试目录**: `tests/`
- **测试类型**: 单元测试
- **Mock 策略**: Mock 外部 API 调用

### DeerFlow

- **框架**: pytest
- **测试目录**: `backend/tests/`
- **测试类型**:
  - 单元测试
  - 集成测试 (`test_client_live.py`)
  - 回归测试 (Docker sandbox, provisioner)
- **CI**: GitHub Actions
- **边界测试**: `test_harness_boundary.py` - 确保 harness 不导入 app

### 对比总结

| 特性 | Agent Studio | DeerFlow |
|------|-------------|----------|
| **测试框架** | pytest | pytest |
| **CI/CD** | 未配置 | GitHub Actions |
| **回归测试** | 无 | 有 (sandbox, provisioner, boundary) |
| **集成测试** | 无 | 有 (client live) |
| **覆盖率** | 基础 | 全面 |

---

## 12. Agent Studio 有而 DeerFlow 没有的功能

1. **Agent 团队系统** (`s09_agent_teams/`)
   - 角色分配器 (`role_assigner.py`)
   - 团队协调器 (`team_coordinator.py`)
   - 工作分发器 (`work_distributor.py`)
   - 质量关卡 (`quality_gate.py`)

2. **团队通信协议** (`s10_team_protocol/`)
   - 异步邮箱 (`async_mailbox.py`)
   - 消息总线 (`message_bus.py`)
   - 冲突解决器 (`conflict_resolver.py`)
   - SLA 管理 (`sla.py`)

3. **Git Worktree 隔离** (`s12_worktree_isolation/`)
   - 分支管理器 (`branch_manager.py`)
   - 隔离沙箱 (`isolated_sandbox.py`)
   - 合并解决器 (`merge_resolver.py`)

4. **自主 Agent 系统** (`s11_autonomous_agent/`)
   - 目标引擎 (`goal_engine.py`)
   - 目标分解器 (`goal_decomposer.py`)
   - 决策引擎 (`decision_engine.py`)

5. **更细粒度的工具权限系统**
   - HMAC 签名验证
   - 每轮调用次数限制
   - 危险命令检测

---

## 13. DeerFlow 有而 Agent Studio 没有的功能

1. **完整的记忆系统** (`agents/memory/`)
   - 长期记忆存储
   - 自动记忆更新
   - 事实提取和管理
   - LLM 驱动的摘要

2. **IM 渠道集成** (`app/channels/`)
   - Telegram Bot
   - Slack Socket Mode
   - 飞书/Lark
   - 企业微信

3. **完整的沙箱系统** (`sandbox/`, `community/aio_sandbox/`)
   - Docker 容器隔离
   - 虚拟路径系统
   - AioSandbox 支持
   - 代码搜索 (grep)

4. **技能系统** (`skills/`)
   - SKILL.md 定义格式
   - 技能发现和加载
   - 渐进式技能加载

5. **MCP 完整支持** (`mcp/`)
   - OAuth token 流
   - 自动缓存失效
   - 多服务器管理

6. **Middleware 链**
   - 14 个内置中间件
   - 可插拔的 Guardrail
   - 自动标题生成
   - TodoList 管理
   - 循环检测

7. **嵌入式客户端** (`client.py`)
   - 无需 HTTP 服务
   - 直接 Python API 访问
   - Gateway API 等价方法

8. **ACP 支持** (Agent Communication Protocol)
   - 外部 Agent 调用
   - ACP 工具集成

9. **上下文摘要** (`agents/middlewares/summarization_middleware.py`)
   - 自动对话摘要
   - 上下文压缩

10. **社区工具** (`community/`)
    - Tavily 搜索
    - Jina AI 网页获取
    - Firecrawl 爬虫
    - DuckDuckGo 图片搜索
    - BytePlus InfoQuest

---

## 14. 可以从 DeerFlow 借鉴的设计思路

### 14.1 Middleware 链模式

**位置**: `backend/packages/harness/deerflow/agents/middlewares/`

**借鉴价值**: Agent Studio 的 Agent Loop 可以通过 Middleware 模式解耦功能。

**具体实现**:
```python
# 参考 DeerFlow 的 middleware 基类
class AgentMiddleware(ABC):
    def before_model(self, state: AgentState) -> AgentState:
        pass
    
    def after_model(self, state: AgentState, output: AIMessage) -> AIMessage:
        pass
```

### 14.2 记忆系统

**位置**: `backend/packages/harness/deerflow/agents/memory/`

**借鉴价值**: Agent Studio 缺乏长期记忆能力。

**核心组件**:
- `MemoryStorage` - 存储抽象
- `MemoryUpdater` - LLM 驱动的更新
- `MemoryQueue` - 异步队列

### 14.3 沙箱抽象

**位置**: `backend/packages/harness/deerflow/sandbox/`

**借鉴价值**: Agent Studio 的工具安全可以升级为完整的沙箱系统。

**核心设计**:
```python
class Sandbox(ABC):
    @abstractmethod
    async def execute_command(self, command: str) -> SandboxResult
    
    @abstractmethod
    async def read_file(self, path: str) -> str
```

### 14.4 IM 渠道集成

**位置**: `backend/app/channels/`

**借鉴价值**: Agent Studio 可以通过类似架构扩展到 IM 平台。

**核心抽象**:
```python
class Channel(ABC):
    @abstractmethod
    async def start(self) -> None
    
    @abstractmethod
    async def send(self, message: OutboundMessage) -> None
```

### 14.5 嵌入式客户端

**位置**: `backend/packages/harness/deerflow/client.py`

**借鉴价值**: Agent Studio 可以提供类似的嵌入式使用方式。

**设计思路**:
```python
class AgentStudioClient:
    def chat(self, message: str) -> str:
        # 直接调用 core 模块，无需 HTTP
```

---

## 借鉴优先级表格

| 优先级 | 功能 | 理由 | 改造难度 | 参考文件 |
|--------|------|------|----------|----------|
| 1 | **Middleware 链模式** | 解耦 Agent Loop 功能，提高扩展性 | 中 | `deerflow/agents/middlewares/` |
| 2 | **长期记忆系统** | 提供跨会话记忆能力，Agent Studio 完全缺失 | 中 | `deerflow/agents/memory/` |
| 3 | **沙箱抽象层** | 提升工具执行安全性，支持容器隔离 | 高 | `deerflow/sandbox/`, `deerflow/community/aio_sandbox/` |
| 4 | **技能系统 (SKILL.md)** | 标准化技能定义，支持渐进加载 | 低 | `deerflow/skills/` |
| 5 | **MCP 完整集成** | 标准化工具集成协议，生态兼容 | 中 | `deerflow/mcp/`, `langchain-mcp-adapters` |

### 详细说明

**优先级 1: Middleware 链模式**
- **理由**: Agent Studio 的 Agent Loop 功能耦合在 `agent_loop.py` 中，通过 Middleware 可以将事件处理、工具执行、安全检查等功能解耦。
- **实现建议**: 参考 DeerFlow 的 `AgentMiddleware` 基类和 `make_lead_agent()` 中的链式组装。

**优先级 2: 长期记忆系统**
- **理由**: Agent Studio 的 `s06_context_compression/` 只有上下文压缩，缺乏跨会话的长期记忆。
- **实现建议**: 移植 `MemoryStorage` + `MemoryUpdater` + `MemoryQueue` 架构，适配 Agent Studio 的类型系统。

**优先级 3: 沙箱抽象层**
- **理由**: Agent Studio 的 `security_gate.py` 只有基础安全检查，需要完整的沙箱隔离。
- **实现建议**: 先实现 `Sandbox` 抽象接口，再集成 `aio_sandbox` 或类似方案。

**优先级 4: 技能系统**
- **理由**: Agent Studio 有 `s05_skills/` 目录，但实现较简单，可以参考 SKILL.md 格式。
- **实现建议**: 采用 DeerFlow 的 `SKILL.md` frontmatter 格式，增强技能发现和加载机制。

**优先级 5: MCP 完整集成**
- **理由**: MCP 正在成为工具集成的标准协议，Agent Studio 应当支持。
- **实现建议**: 直接使用 `langchain-mcp-adapters` 库，或参考其实现自定义集成。

---

*报告生成时间: 2026/04/06*
