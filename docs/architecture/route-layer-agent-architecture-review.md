# Route 层 Agent 架构评估报告

## 总体结论

当前 route 层能支撑早期产品运行，但已经偏厚，不适合作为成熟 agent 平台的长期架构。

主要问题不是路由文件数量，而是 `backend/api` 同时承担了 HTTP/WebSocket/Feishu 入口、agent runtime 构造、tool registry 注册、MCP 同步、plan runner 生命周期、sub-agent worker 消费、多 agent policy 和进程内运行状态管理。

理想结构应更接近：

```text
HTTP / WebSocket / Feishu Adapter
    -> Command DTO / Request Model
    -> Application Service
    -> Agent Runtime / Core
    -> Ports / Adapters / Storage
```

当前结构更接近：

```text
Route
    -> Runtime 拼装
    -> Tool 注册
    -> Queue / Worker / State / Policy
    -> Core
```

## 做得好的地方

- 小型 REST route 拆分还可以，例如 sessions、workspaces、providers。
- `backend/api/app.py` 启动流程直观，能看清 DB、Redis、metrics、runtime、task queue 初始化。
- `AgentLoop`、`ToolRegistry`、`MCPToolBridge` 的核心方向是对的。
- 已经有拆分苗头，例如 `websocket_runtime.py`、`websocket_support.py`、`workspace_service.py`。
- 多数 API 有 Pydantic schema 和结构化错误码。

## 主要问题

### 1. `app.py` 过重

`backend/api/app.py` 同时负责 DB、Redis、metrics、runtime、task queue、scheduler、Feishu handler、morning report 初始化。

- `backend/api/app.py:35`
- `backend/api/app.py:130`

`backend/api/router.py`、`backend/api/deps.py`、`backend/api/routes/__init__.py` 当前都是空文件，实际路由聚合直接发生在 `app.py` 中。风险是新增入口容易绕过统一鉴权、prefix、依赖和错误策略。

### 2. Route 层承载过多 agent orchestration

`backend/api/routes/chat_completions.py:90` 直接完成 message 转换、adapter 获取、工具注册、MCP sync、`AgentLoop` 构造和 SSE 输出。

`backend/api/routes/websocket.py:130` 混合 WebSocket 连接、loop 缓存、plan runner、resume、knowledge run 和任务启动。

这些职责已经超过薄 HTTP adapter 的范围。

### 3. API/Core 依赖方向倒置

`backend/core/task_queue_consumer.py:1` 从 `backend.api.task_queue_consumer` re-export。

`backend/sub_worker.py:15` 非 HTTP worker 也直接 import API consumer。

这违反了 `backend/api` 作为 HTTP 入口层的边界，也说明 task consumer 不该放在 API 包里。

### 4. 多 agent policy 放错层

`backend/api/routes/feishu_multi_agent_policy.py:45` 在 API route 包中定义子 agent policy、模板、工具白名单和 prompt hint。

这类策略应属于 core/runtime policy profile。Feishu route 应只选择 profile，不应定义平台级多 agent policy。

### 5. 运行状态依赖进程内 dict

`backend/api/routes/websocket.py:33` 保存 `_loops`、`_plan_runners`、`_tasks`。

`backend/api/routes/feishu_handler.py:70` 保存 `_sessions`、`_plan_runners`、`_pending_resume`。

这对多 worker、重启恢复和水平扩展不友好。

## 对比成熟 Agent 架构

参考对象：

- OpenAI Agents SDK: <https://openai.github.io/openai-agents-python/>
- LangGraph: <https://docs.langchain.com/oss/python/langgraph/overview>
- Microsoft Agent Framework: <https://learn.microsoft.com/en-us/agent-framework/overview/>

成熟 agent 架构通常把以下能力放在 runtime/application 层：

- handoff / orchestration
- state / checkpoint
- guardrails / policy
- tracing / observability
- human-in-the-loop
- durable execution
- event stream

本项目中这些能力已经有雏形，但入口层还没有瘦下来，导致 HTTP/Feishu/WebSocket route 直接参与 runtime 组装和状态管理。

## 建议优先级

### P0

- 将 `backend/api/task_queue_consumer*.py` 移出 API 包。
- 消除 `backend/core -> backend/api` 的反向依赖。
- 新增 `AgentInvocationService` / `PlanRunService`，收拢 loop/runner 构造、工具注册、MCP sync、checkpoint 恢复。

### P1

- 将 `feishu_multi_agent_policy.py` 移到 `core/s04_sub_agents` 或 `core/s05_skills`。
- 给 `AgentRuntime` / `PlanExecuteRunner` 补公共 resume API，避免访问 `_adapter`、`_tool_registry` 等私有字段。
- 清理绕过 `__init__.py` 的内部模块 import。

### P2

- 引入 `RunRegistry` / `SessionRuntimeRegistry`，区分 durable state 和 process-local handle。
- 统一 `AgentRunEvent`、`PlanEvent`、`SubAgentEvent`。
- SSE、WebSocket、Feishu 卡片、日志都从统一事件模型转换。

## 最终判断

route 层当前是“集成入口 + 应用服务 + runtime factory + worker 编排”的混合体。

短期可用，长期必须瘦身。下一步不要继续往 route 里加能力，应优先把 runtime 构造、任务消费、多 agent policy 和运行状态管理移出 `backend/api`。
