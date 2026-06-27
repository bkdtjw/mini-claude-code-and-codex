# Agent Studio 架构评估报告

## 执行摘要

### 总体评价

Agent Studio 是一个基于 Python + FastAPI + Pydantic v2 构建的多 Agent 编排系统，核心采用 ReAct 循环 + Plan-and-Execute 双模式架构，支持 WebSocket 实时通信、飞书（Feishu/Lark）IM 集成、OpenAI 兼容 API，以及子 Agent 隔离运行、技能系统、上下文压缩等高级特性。

**优势：**
- 架构设计先进：三层上下文压缩（L1/L2/L3）、消息 Zone 分层、事件驱动解耦、安全门控工具执行
- 工程实践规范：全量 type hints、Pydantic v2 类型系统、模块分层清晰（s01-s12）
- 多模态接入：WebSocket 流式、飞书卡片交互、OpenAI 兼容 SSE、定时任务调度
- 生产级特性：Redis pub/sub 跨 worker 广播、任务队列租约机制、计划检查点恢复

**劣势：**
- 多个模块（s09_agent_teams、s10_team_protocol、s11_autonomous_agent）完全为空，架构缺口明显
- Token 计数使用粗糙的 `len(text)//4` 估算，中文场景误差可达 50-100%
- 长期记忆使用文件 JSON + 关键词匹配，与行业标准的向量数据库方案差距明显
- 代码文件膨胀：`feishu_handler.py`（512 行）、`websocket.py`（431 行）远超 200 行限制

**风险：**
- 无速率限制中间件，LLM API 调用端点存在滥用和成本失控风险
- WebSocket 无认证和心跳机制，存在安全漏洞和连接稳定性问题
- 飞书 webhook 无时间戳验证，存在重放攻击风险
- Redis 和 PostgreSQL 状态无分布式事务保障，可能出现双写不一致

### 关键发现概述

| 维度 | 评分 | 关键发现 |
|------|------|---------|
| Agent 编排层 | 8/10 | ReAct + Plan-and-Execute 双模式成熟，但缺少 Reflexion/LATS 等高级模式 |
| Route 层 | 6/10 | FastAPI 基础扎实，但依赖注入不足、速率限制缺失、WebSocket 无认证 |
| 高级特性 | 8.5/10 | 子 Agent 隔离、技能系统、上下文压缩设计领先，但 s09-s11 模块为空 |
| 类型系统 | 8/10 | Pydantic v2 使用规范，但存在 Schema 重复和 legacy fallback 路径 |
| 上下文管理 | 7/10 | 三层压缩架构创新，但 token 估算不准、无增量压缩、记忆系统薄弱 |
| 设计模式 | 6/10 | ReAct/Plan-and-Execute 实现完善，但 Self-Reflection/层次化 Agent 缺失 |
| 路由最佳实践 | 5/10 | 与 FastAPI/WebSocket/MQ 最佳实践差距明显，多个中间件为空 |

---

## 1. Agent 编排层架构分析

### 1.1 主 Agent 循环设计

Agent Studio 的主循环（`AgentLoop.run`）遵循经典的 ReAct（Reasoning + Acting）模式，定义在 `backend/core/s01_agent_loop/agent_loop_run.py` 中。

**循环流程：**

```
初始化（失败恢复追踪器 + 循环守卫 + 日志上下文）
  → 迭代（最多 max_iterations 次）:
    1. 上下文压缩（LayeredCompressor.compress）
    2. 守卫提示注入（AgentLoopGuard，死胡同反射/最终收敛）
    3. LLM 请求构建（build_llm_request，分区消息组装）
    4. 流式 LLM 调用（complete_with_stream，emit text_delta/tool_call 事件）
    5. 响应处理（追加 assistant 消息，无 tool_calls 则返回）
    6. 工具执行流水线:
       - 失败恢复预过滤（跳过重复失败调用）
       - 安全授权（SecurityGate：signed/rejected/pending_approval）
       - 自动审批（LLM 审查 pending_approval 调用）
       - 人工审批（asyncio.Event 等待外部触发）
       - 按副作用分区（read-only 并行，write 串行）
       - 合并结果并注入失败恢复上下文
    7. 工具结果追加到历史
  → 终止（返回最终答案 或 抛出 LOOP_MAX_ITERATIONS/LOOP_ABORTED）
```

**关键代码引用：**
- 主循环：`backend/core/s01_agent_loop/agent_loop_run.py:30-194`
- 循环守卫：`backend/core/s01_agent_loop/agent_loop_guard.py`
- 消息历史：`backend/core/s01_agent_loop/message_history.py`

### 1.2 子 Agent 机制

子 Agent 机制通过 `spawn_agent` 工具实现，支持并行异步执行和结果复用。

**任务生命周期：**

1. **任务准备**（`spawn_agent_prepare.py`）：
   - 验证 `SubAgentPolicy`（allowed_specs、max_concurrent、max_depth）
   - 解析内联模板（research-specialist、code-reader、implementer 等 9 种）
   - 计算 `max_iterations`（受 policy cap 限制）

2. **任务去重**（`spawn_agent.py:_split_reused_tasks`）：
   - 基于任务参数的 SHA256 `reuse_key`
   - 复用同一父任务下已成功的相同子任务

3. **任务提交**：验证并发容量后提交到 `TaskQueue`

4. **等待与轮询**（`spawn_agent_wait.py`）：
   - 全局超时 = `min(max(timeout)*2, 600s)`
   - 进度事件：`sub_agent_spawned` → `sub_agent_completed`/`sub_agent_failed`

5. **结果格式化**（`spawn_agent_support.py`）：
   - 聚合所有子 Agent 结果为单个 `ToolResult`
   - 大输出自动归档；全部失败时标记 error

**关键代码引用：**
- `backend/core/s02_tools/builtin/spawn_agent.py`
- `backend/core/s02_tools/builtin/spawn_agent_prepare.py`
- `backend/core/s02_tools/builtin/spawn_agent_wait.py`
- `backend/core/s02_tools/builtin/spawn_agent_support.py`
- `backend/core/s02_tools/builtin/spawn_agent_templates.py`
- `backend/core/s02_tools/builtin/spawn_agent_governance.py`
- `backend/core/s04_sub_agents/isolated_runner.py`

### 1.3 工具调用编排

工具执行采用多阶段安全与调度流水线：

**阶段 1：失败恢复预过滤**（`failure_recovery.py`）
- `ToolFailureRecoveryTracker` 追踪调用签名（tool_name + 规范化参数 hash）
- 超过 `max_consecutive_tool_failures` 阈值后跳过重复调用
- 错误结果注入恢复上下文（失败次数、指纹、策略建议）

**阶段 2：安全授权**（`security_gate.py`）
- HMAC-SHA256 签名，每会话随机密钥
- 防重放攻击（verified_sequences 追踪）
- 拒绝未知工具、非允许工具、超出 `max_calls_per_turn` 的调用

**阶段 3：自动审查**（`tool_review.py`）
- LLM 审查 pending_approval 调用
- 上下文感知：知道 plan_goal、current_step、step_description
- 决策：auto_approve / auto_reject / require_human

**阶段 4：人工审批**（`agent_loop_approval.py`）
- 发出 `tool_approval_required` 事件
- 通过 `approve_tool_call`/`reject_tool_call` 外部触发

**阶段 5：执行调度**（`tool_batching.py` + `executor.py`）
- `partition_by_side_effect`：按 `ToolDefinition.side_effect` 分离读写
- Read-only：`execute_signed_batch()` 通过 `asyncio.gather` 并行执行
- Write：`execute_signed_serial()` 串行执行避免竞态
- `merge_results`：按原始顺序重组结果

**阶段 6：输出截断**
- 标准工具截断至 12K 字符（头+尾标记）
- 聚合工具（spawn_agent、orchestrate_agents）48K 字符

**关键代码引用：**
- `backend/core/s02_tools/executor.py`
- `backend/core/s02_tools/security_gate.py`
- `backend/core/s01_agent_loop/tool_batching.py`
- `backend/core/s01_agent_loop/failure_recovery.py`
- `backend/core/s01_agent_loop/tool_review.py`
- `backend/core/s01_agent_loop/agent_loop_approval.py`

### 1.4 上下文压缩集成

上下文压缩在每次 LLM 调用前触发，采用三层递进式架构：

**L1 - Artifact 归档**（`level1_artifact.py`）
- 单个工具结果 >500 tokens 时写入文件系统（`data/artifacts/{session_id}/`）
- 消息中替换为摘要 + 归档路径

**L2 - 历史消息紧凑化**（`level2_compact.py`）
- 上下文使用率 >50% 时触发
- 保留最近 6 条消息不变
- 排除 `read_history` 工具结果（防止破坏历史查询能力）

**L3 - LLM 结构化摘要**（`level3_summary.py`）
- 上下文使用率 >70% 时触发
- XML 格式结构化摘要：`<goal>`、`<constraints>`、`<identifiers>`、`<decisions>`、`<failures>`、`<pending>`、`<narrative>`
- 原始消息写入 `data/sessions/{session_id}/` 作为无损备份
- LLM 失败时降级为 fallback summary

**最终回退**：使用率 >90% 时强制再次摘要

**阈值配置**（`LayeredCompressorConfig`）：
- `threshold_l2 = 0.5`（50%）
- `threshold_l3 = 0.7`（70%）
- `threshold_final = 0.9`（90%）
- `max_context_tokens = 180000`

**关键代码引用：**
- `backend/core/s06_context_compression/layered_compressor.py`
- `backend/core/s06_context_compression/level1_artifact.py`
- `backend/core/s06_context_compression/level2_compact.py`
- `backend/core/s06_context_compression/level3_summary.py`
- `backend/core/s06_context_compression/compressor.py`（legacy）
- `backend/core/s06_context_compression/token_counter.py`
- `backend/core/s06_context_compression/threshold_policy.py`

### 1.5 错误处理与恢复

错误处理是多层级的：

| 层级 | 机制 | 文件 |
|------|------|------|
| 工具级 | try-except 包裹，异常转 error ToolResult | `executor.py` |
| 失败恢复 | 追踪连续失败，跳过重复调用，注入恢复提示 | `failure_recovery.py` |
| 循环守卫 | 死胡同反射提示 + 最终收敛提示 | `agent_loop_guard.py` |
| 计划级 | 每步独立超时（600s）和迭代限制（30），失败继续下一步 | `plan_execute_runner.py` |
| Recon 降级 | JSON 解析失败回退文本提取，完全失败回退轻量计划 | `plan_recon_parse.py` |
| 检查点恢复 | 每阶段持久化，自动恢复中断步骤 | `plan_checkpoint_store.py`、`plan_resume.py` |
| 中止机制 | `_aborted` 标志 + 信号所有审批事件 | `AgentLoop.abort` |
| 孤儿工具修复 | 错误退出时补全未执行 tool_call 的合成错误结果 | `agent_loop_support.py:patch_orphan_tool_calls` |

### 1.6 设计亮点

1. **层次化 Plan & Execute 架构**：低层 ReAct 循环（`AgentLoop`）+ 高层 `PlanExecuteRunner`（recon → plan → approve → execute），简单任务高效运行，复杂任务结构化规划。
2. **三层上下文压缩（L1/L2/L3）**：递进式压缩，每层有降级策略，信息永不丢失（原始消息归档到磁盘）。
3. **安全优先的工具执行流水线**：HMAC 签名 + 重放保护 + 自动审批策略 + LLM 风险审查 + 强制人工审批，读写分离实现安全并行。
4. **智能任务路由**：`plan_task_routing.py` 自动分类用户请求（代码/商业研究/网页研究/通用），自动选择规划策略。
5. **子 Agent 去重与复用**：基于 SHA256 reuse_key 复用已成功子任务，避免冗余计算。
6. **模板化子 Agent 角色**：9 种预定义内联模板，带精选工具集和迭代预算。
7. **收敛监控**：`ConvergenceMonitor` 在 5/8/10 次工具调用处注入递进提示，结合 `AgentLoopGuard` 防止无限循环。
8. **全面检查点与恢复**：每阶段持久化，自动恢复中断步骤，`PlanControlStore` 支持外部暂停/恢复/停止。
9. **结构化消息语义**：`MessageKind` 定义 7 种语义类别，支持精确的上下文组装和过滤。
10. **优雅降级无处不在**：JSON 解析失败回退文本提取、recon 失败回退轻量计划、LLM 摘要失败回退截断摘要、检查点失败仅记录不阻塞。

### 1.7 潜在问题

1. **复杂继承链**：`PlanExecuteRunner` 使用多个 mixin（`PlanResumeMixin`、`PlanExecuteRunnerStateMixin`、`PlanExecuteRunnerNotificationsMixin`、`PlanExecuteRunnerStepsMixin`）分散在多个文件中，难以追踪方法来源。
2. **重复压缩系统**：`ContextCompressor`（legacy）和 `LayeredCompressor`（new）同时存在，AgentLoop 初始化两者但主循环只用后者。
3. **魔法数字散落**：收敛阈值 5/8/10、artifact 归档 500 tokens、工具截断 12K 字符、步骤超时 600s 等硬编码在多处，无集中配置。
4. **子 Agent 机制重叠**：`spawn_agent`（TaskQueue 异步并行）、`dispatch_agent`（直接 AgentLoop 派生）、`orchestrate_agents`（依赖图逻辑）三者功能重叠，维护负担大。
5. **压缩静默失败**：`LayeredCompressor` 多处 `except Exception: return list(messages)`，上下文可能无限增长而不告警。
6. **Token 计数启发式**：`TokenCounter` 使用 `len(text)//4`，中文内容严重低估（中文 1-2 字符/token），可能导致压缩不及时。
7. **计划审批阻塞**：默认需要显式用户审批，自动化工作流/API 使用场景不适用。
8. **嵌套 AgentLoop 无深度限制**：Plan 步骤创建嵌套 AgentLoop，可进一步调用 `spawn_agent`，无显式深度限制或资源核算。
9. **消息历史原地突变**：`agent_loop_run.py` 中 `messages[:] = await compressor.compress(...)`，其他组件持有原始列表引用可能出问题。
10. **工具结果合并不保留执行顺序**：`merge_results` 按 `tool_call_id` 重组，但不保留执行顺序信息。

---

## 2. Route 层架构分析

### 2.1 HTTP API 路由组织

Agent Studio 采用混合路由风格：RESTful 路由（sessions、providers、mcp、knowledge、metrics、logs、workspaces）遵循标准 CRUD 模式；非 RESTful 路由包括 OpenAI 兼容的 `/v1/chat/completions`、WebSocket `/ws/{session_id}`、飞书 webhook `/api/feishu/event` 和 `/api/feishu/card_action`、Prometheus `/metrics`。

**认证策略：**
- 受保护路由使用 `Depends(verify_token)` 在 router 级别配置
- 公共路由：`/health`、`/health/live`、`/health/ready`、`/v1/chat/completions`、所有飞书 webhook

**路由注册：** 集中注册在 `backend/api/app.py` 的 `app.include_router()`。

**问题：**
- `backend/api/router.py` 为空文件（0 字节），路由直接在 `app.py` 中注册，未模块化
- 无 API 版本前缀，不利于 API 演进
- 无请求体大小限制

**关键代码引用：**
- `backend/api/app.py`
- `backend/api/routes/sessions.py`
- `backend/api/routes/providers.py`
- `backend/api/routes/mcp.py`
- `backend/api/routes/knowledge.py`
- `backend/api/routes/chat_completions.py`

### 2.2 WebSocket 实时通信

WebSocket 使用单一端点 `/ws/{session_id}`，由 `ConnectionManager` 管理：

**ConnectionManager 状态：**
- `_connections`：WebSocket 对象字典
- `_loops`：AgentLoop 实例字典
- `_plan_runners`：PlanExecuteRunner 实例字典
- `_loop_settings`：循环设置
- `_tasks`：asyncio Task 字典

**消息类型协议：**
- `run`：启动 Agent 循环
- `plan_execute`：计划模式
- `plan_approve`/`plan_reject`/`plan_resume`/`plan_discard`：计划控制
- `tool_approve`/`tool_reject`：工具审批
- `abort`：取消执行

**跨 Worker 广播：**
- `websocket_pubsub.py` 实现 Redis pub/sub
- `publish_session_message()` 发布到 Redis 频道
- `forward_session_messages()` 订阅并转发跨 worker 消息

**计划执行渲染：**
- `WsPlanRenderer` 转发计划生命周期事件（recon、计划创建、步骤更新、修订、完成）为 WebSocket 消息

**问题：**
- 无心跳机制（协议级 `ping_interval` 或应用级心跳），代理环境下易超时断开
- 广播逐个连接发送，未使用 `websockets.broadcast()` 优化
- 无连接数限制
- WebSocket 握手时无 token 验证
- `ws_endpoint` 长达 243 行，处理 10+ 种消息类型，违反单文件 200 行约束

**关键代码引用：**
- `backend/api/routes/websocket.py`
- `backend/api/routes/websocket_runtime.py`
- `backend/api/routes/websocket_support.py`
- `backend/api/routes/websocket_pubsub.py`

### 2.3 飞书集成

飞书集成采用多路由 webhook 架构：

**路由分层：**
1. `/api/feishu/event`（`feishu.py`）：主事件回调，处理 URL 验证、HMAC-SHA256 签名验证、菜单事件、消息事件
2. `/api/feishu/card_action`、`/api/feishu/plan_approval`、`/api/feishu/tool_approval`（`feishu_card_action.py`）：交互卡片按钮回调，使用 `CardActionDispatcher` 注册表模式
3. `/feishu/events`（`feishu_events.py`）：加密事件分发器，支持 payload 解密

**核心处理器**（`FeishuMessageHandler`）：
- 事件去重：Redis `FeishuEventDeduplicator`
- 并发控制：每 `chat_id` 一个 `asyncio.Lock`
- 会话持久化：`SessionStore`
- 计划执行：`PlanExecuteRunner`
- 斜杠命令解析：`/plan`、`/`
- 菜单状态管理：`FeishuMenuState`
- 知识库路由
- 工具审批卡片渲染

**消息处理优先级流水线：**
```
去重检查 → Bot 过滤 → 知识库路由 → 计划恢复门 → 活跃计划控制 → 计划请求解析 → 斜杠命令 → 计划模式检查 → 普通 Agent 循环
```

**问题：**
- `FeishuMessageHandler` 混合过多职责（消息路由、计划执行、知识库、菜单状态、会话管理），`handle_message` 长达 138 行
- 两个飞书事件路由（`/feishu/events` 和 `/api/feishu/event`）功能重叠
- 无时间戳验证，存在重放攻击风险
- 无 webhook 限流
- 卡片操作 fallback 逻辑脆弱

**关键代码引用：**
- `backend/api/routes/feishu.py`
- `backend/api/routes/feishu_handler.py`
- `backend/api/routes/feishu_handler_support.py`
- `backend/api/routes/feishu_runtime.py`
- `backend/api/routes/feishu_plan_support.py`
- `backend/api/routes/feishu_plan_control.py`
- `backend/api/routes/feishu_card_action.py`
- `backend/api/routes/feishu_events.py`

### 2.4 请求到 Agent 的流转

```
1. Route handler 接收请求/WebSocket 消息
2. REST: Pydantic schema 验证输入
   WebSocket: parse_loop_settings() 验证设置
   Feishu: extract_text() 提取消息内容
3. AgentLoop 创建: create_loop() (websocket) / build_agent_loop() (feishu) / 直接实例化 (chat_completions)
4. AgentLoop 初始化: AgentConfig + LLMAdapter + ToolRegistry + 可选 MCPToolBridge + 可选 CheckpointFn
5. loop.run(user_message) → run_agent_loop()
6. 循环迭代: 压缩上下文 → 构建 LLM 请求 → 流式响应 → 发出事件 → 执行工具调用 → 追加结果 → 重复
7. 事件通过 loop._emit() 转发到 WebSocket/Feishu 订阅者
8. Plan 模式: PlanExecuteRunner 编排多步骤执行（recon → plan → checkpoint → resume）
```

### 2.5 中间件模式

当前中间件栈（按顺序）：
1. `RequestTraceMiddleware`：分布式追踪（`trace_context()`）、注入 `X-Trace-Id`、记录 HTTP 延迟指标、记录请求时长
2. `CORSMiddleware`：允许所有来源/方法/头部
3. `verify_token`（per-route dependency）：Bearer token 认证，`secrets.compare_digest()` 防止时序攻击

**问题：**
- `rate_limit.py` 和 `error_handler.py` 为空文件（0 字节）
- 无全局异常处理中间件，每个路由重复 try-except
- 错误处理是路由级别的，非集中式

**关键代码引用：**
- `backend/api/middleware/auth.py`
- `backend/api/middleware/request_trace.py`
- `backend/api/middleware/rate_limit.py`（空）
- `backend/api/middleware/error_handler.py`（空）

### 2.6 异步任务队列

任务队列实现于 `backend/core/task_queue.py`（`TaskQueue`），Redis 后端持久化：

**集成点：**
1. `init_task_queue()`（`lifespan_support.py`）：应用启动时创建队列，附加到 `app.state.task_queue`
2. `SubAgentConsumerContext`：持有队列和 agent_runtime
3. `consume_next_sub_agent_task()`：worker 认领任务、执行、完成/失败
4. `execute_sub_agent_task()`：处理不同任务类型（`knowledge_ingest`、`knowledge_ingest_batch`、`knowledge_ingest_local_batch`、通用子 Agent 任务）
5. 心跳机制：`_heartbeat_loop()` 每 15 秒续租，60 秒扩展

**任务提交来源：**
- 知识库上传（`knowledge.py`）
- 飞书知识流（`feishu_knowledge_tasks.py`）
- 内置工具（`spawn_agent.py`）

**治理策略：**
- `enforce_child_loop_permission()`：readonly 模式移除写工具
- `apply_child_loop_budget()`：限制 max_iterations
- `build_sub_agent_complete_result()`：大输出强制归档

**问题：**
- 使用 Redis List 而非 Streams，缺少消费者组、消息重放、偏移量管理
- 无死信队列
- 无任务优先级
- 无队列深度监控
- 任务结果无回调机制（只能轮询）

**关键代码引用：**
- `backend/core/task_queue.py`
- `backend/core/task_queue_types.py`
- `backend/api/task_queue_consumer.py`
- `backend/api/lifespan_support.py`

### 2.7 设计亮点

1. **关注点分离**：`backend/api/routes/` 只处理 HTTP/WS 协议、请求验证和响应格式化，核心逻辑通过适配器模式注入。
2. **事件驱动架构**：`AgentLoop` 发出 `AgentEvent` 对象，由 WebSocket 发送器、飞书卡片渲染器和计划渲染器消费。
3. **多模态会话支持**：同一 `AgentLoop` 核心支持 WebSocket（实时流式）、飞书（异步消息卡片）、OpenAI 兼容 HTTP（SSE 流式）。
4. **计划执行为一等公民**：WebSocket 和飞书都支持 `PlanExecuteRunner`，带检查点/恢复、审批门、暂停/停止控制、逐步进度报告。
5. **Pub/Sub 水平扩展**：WebSocket 使用 Redis pub/sub 实现多 worker 广播。
6. **飞书并发控制**：每 `chat_id` 使用 `asyncio.Lock` 防止共享 AgentLoop 实例的竞态条件。
7. **工具审批交互卡片**：飞书渲染带 approve/reject 按钮的审批卡片；WebSocket 发送 `tool_approval_required` 事件供前端渲染。
8. **MCP 桥接集成**：`MCPToolBridge` 在循环创建时将 MCP 服务器工具同步到 `ToolRegistry`。
9. **上下文压缩管道**：`LayeredCompressor` 在每次 LLM 调用前自动压缩消息历史。
10. **子 Agent 治理**：预算上限、权限限制和 artifact 下沉防止失控子 Agent 执行。

### 2.8 潜在问题

1. **无全局异常处理中间件**：每个路由有相同的 try-except 样板代码。
2. **速率限制和错误处理为空文件**：`rate_limit.py` 和 `error_handler.py` 为 0 字节。
3. **飞书事件处理器使用 fire-and-forget**：`asyncio.create_task()` 无任务追踪或清理，高负载下可能泄漏任务。
4. **ConnectionManager 内存字典**：WebSocket 连接和 AgentLoop 存储在内存字典中，多进程环境下需依赖 pub/sub 回退。
5. **飞书去重依赖 Redis**：Redis 不可用时回退到错误，可能导致重复处理或消息丢失。
6. **Chat completions 无会话持久化**：OpenAI 兼容 API 调用不保存消息历史。
7. **router.py 为空**：路由直接在 `app.py` 中注册，未模块化。
8. **FeishuMessageHandler 职责过重**：应考虑拆分为更小的处理器。
9. **飞书 webhook 无请求体大小限制**：大 payload 可能导致内存问题。
10. **WebSocket plan runners 和 loops 生命周期不同**：存储在同一 ConnectionManager 中，断开时可能状态不一致。

---

## 3. 高级特性架构分析

### 3.1 子 Agent 隔离运行

子 Agent 隔离采用三层隔离模型：

**系统提示隔离**（`isolated_runner.py`）：
- `_build_sub_agent_system_prompt()` 为每个子 Agent 构建独立系统提示
- 子 Agent 只能看到当前分配的任务和显式提供的依赖结果
- 无法访问主对话历史，也无法与其他子 Agent 直接通信

**工具注册表隔离**（`permission_policy.py`）：
- `build_isolated_registry()` 从父注册表过滤子 Agent 可用工具
- 递归工具（`dispatch_agent`、`orchestrate_agents`）自动排除
- 两级权限：`readonly`（只允许 Read、Bash 只读命令）和 `readwrite`
- Bash 在 readonly 模式下包装为 `readonly_bash`，正则拦截写操作（`rm`、`mv`、`cp`、`sed -i`、`>` 重定向等）

**运行时环境隔离**（`isolated_runner.py`）：
- `IsolatedAgentRuntime` 封装 adapter、父注册表和配置
- 每个子 Agent 获得独立的 `AgentLoop` 实例
- `asyncio.wait_for()` 超时控制（默认 120s）

**两种调度模式：**
- **StaticDagScheduler**（`static_dag.py`）：基于依赖关系的阶段执行，同阶段并行（`asyncio.gather`），支持 `on_dep_failure` 策略（block/proceed）
- **DynamicOrchestrator**（`dynamic_orchestrator.py`）：波浪式动态任务生成，最多 `max_waves=4`，每波最多 `max_concurrent=5`
- **SchedulerSwitch**（`scheduler_switch.py`）：关键词检测自动选择 static/dynamic 模式

**结果契约**（`result_contract.py`）：
- `AgentResultV1` 结构化输出（status、summary、findings、artifacts、next_steps）
- LLM 自动修复：非合法 JSON 时最多 2 次修复尝试
- 修复失败降级为 `unparsed` 状态

**关键代码引用：**
- `backend/core/s04_sub_agents/isolated_runner.py`
- `backend/core/s04_sub_agents/permission_policy.py`
- `backend/core/s04_sub_agents/static_dag.py`
- `backend/core/s04_sub_agents/dynamic_orchestrator.py`
- `backend/core/s04_sub_agents/scheduler_switch.py`
- `backend/core/s04_sub_agents/result_contract.py`
- `backend/core/s04_sub_agents/shared_runtime.py`

### 3.2 技能系统

技能系统采用动态加载和运行时注入机制：

**技能定义模型**（`models.py`：`AgentSpec`）：
- 基础字段：id、title、category、description、system_prompt、model、provider
- 运行配置：max_iterations、timeout_seconds、default_mode、allow_modes
- 工具配置：`ToolConfig`（allowed_tools、mcp_servers、tool_overrides）
- 子 Agent 策略：`SubAgentPolicy`（allowed_specs、max_concurrent、max_depth、allow_inline_roles 等）
- 触发模式：`mode` 支持 `"inject"`（注入）或 `"loop"`（独立循环）
- 关键词触发：`trigger_keywords` 用于自动匹配用户输入

**技能加载器**（`loader.py`）：
- 从 `skills/` 目录加载，每个技能一个目录
- `SKILL.md`（Frontmatter YAML + 描述）、`prompt.md`（可选）、`tools.yaml`（可选）、`sub_agents.yaml`（可选）
- ID 必须与目录名匹配

**技能注册表**（`registry.py`）：
- 内存索引，支持按类别搜索、关键词搜索、摘要预览
- 只返回 `enabled=True` 的技能

**按需加载器**（`on_demand_loader.py`）：
- `match(user_text)`：根据 `trigger_keywords` 匹配，返回最多 `inject_limit=2` 个技能消息
- `load_skill(skill_id)`：显式加载，inject 模式加入 pending 队列
- 注入格式：`<skill_context>\n{prompt}\n</skill_context>`，`kind="skill_context"`

**运行时**（`runtime.py`：`AgentRuntime`）：
- `create_loop()`：根据 `AgentSpec` 创建完整 `AgentLoop`
  - 解析 provider 和 model
  - 构建分层系统提示（stable_prompt + skill_prompt）
  - 构建工具注册表（`build_runtime_registry`）
  - 创建 `FilteredBridge` 同步 MCP 工具
  - 注入 `OnDemandSkillLoader` 和 `MemoryIndex`
- `create_loop_inline()`：为内联角色创建临时 `AgentSpec`
- `create_loop_from_id()`：通过 spec_id 查找并创建

**运行时注册表构建**（`runtime_support.py`）：
- `build_runtime_registry()` 动态构建工具注册表
- 调用 `register_builtin_tools` 注册基础工具
- kwargs 反射注入可选依赖
- 过滤不允许的工具（allowed_tools）
- 根据 max_depth 限制递归工具
- 应用工具覆盖（tool_overrides）
- `FilteredBridge`：包装 `MCPToolBridge`，只同步需要的 MCP 服务器

**计划执行模式**（`runtime_plan.py`）：
- `direct`：直接 AgentLoop 模式
- `plan_execute`：PlanExecuteRunner 模式
- `create_runtime_runner()` 根据 spec 的 default_mode 创建对应执行器
- `runtime_plan_patch.py` 的 `patch_plan_runner()` 将 spec 的 max_iterations 和 timeout 注入到 plan runner 的每个步骤

**关键代码引用：**
- `backend/core/s05_skills/models.py`
- `backend/core/s05_skills/runtime.py`
- `backend/core/s05_skills/on_demand_loader.py`
- `backend/core/s05_skills/runtime_support.py`
- `backend/core/s05_skills/runtime_plan.py`
- `backend/core/s05_skills/loader.py`
- `backend/core/s05_skills/registry.py`

### 3.3 上下文压缩多层架构

上下文压缩采用三层递进式架构，由 `LayeredCompressor` 统一协调：

**L1 - 工具结果归档**（`level1_artifact.py`）：
- 单个工具结果 >500 tokens 时自动写入文件系统（`data/artifacts/{session_id}/`）
- 返回精简摘要（提取 JSON 前 3 项或首行）+ 归档路径

**L2 - 历史消息紧凑化**（`level2_compact.py`）：
- 策略：将最旧的大工具结果归档，保留最近 6 条消息不变
- 排除 `read_history` 工具结果
- 已包含 artifact 路径的结果不再归档
- `compact_old_tool_summaries()` 将旧消息中的工具结果替换为 `[工具结果已归档]`

**L3 - 对话历史摘要**（`level3_summary.py`）：
- 上下文超过 70% 时，将最近 6 条之前的所有消息通过 LLM 压缩为结构化摘要
- XML 格式：`goal`、`constraints`、`identifiers`、`decisions`、`failures`、`pending`、`narrative`
- 原始消息写入 `data/sessions/{session_id}/` 作为无损备份
- LLM 调用失败时生成 fallback_summary

**传统压缩器**（`compressor.py`）：
- 基于 `ThresholdPolicy` 的压缩
- 保留最近 N 条消息（`reserve_recent_count=6`）
- `SUMMARY_SYSTEM_PROMPT` 指导 LLM 生成结构化摘要
- LLM 失败时生成截断式 fallback summary

**Token 计数与阈值策略：**
- `token_counter.py`：简单估算（字符数/4），覆盖消息、tool_calls、tool_results、tool definitions
- `threshold_policy.py`：`ThresholdPolicy` 定义压缩触发条件（默认 90% 上下文使用率）

**长期记忆**（`memory_index.py` + `long_term_memory.py`）：
- `MemoryEntry`：trigger、lesson、keywords、source_session、hit_count
- `MemoryIndex.match(query, limit=5)`：基于关键词匹配和命中次数评分
- 在 `build_llm_request()` 中注入为 `<memory_context>` 消息

**垃圾回收**（`artifact_gc.py`）：
- 定期清理超过 7 天的 artifacts 和 sessions 文件

**关键代码引用：**
- `backend/core/s06_context_compression/layered_compressor.py`
- `backend/core/s06_context_compression/level1_artifact.py`
- `backend/core/s06_context_compression/level2_compact.py`
- `backend/core/s06_context_compression/level3_summary.py`
- `backend/core/s06_context_compression/compressor.py`
- `backend/core/s06_context_compression/token_counter.py`
- `backend/core/s06_context_compression/threshold_policy.py`
- `backend/core/s06_context_compression/memory_index.py`
- `backend/core/s06_context_compression/long_term_memory.py`
- `backend/core/s06_context_compression/artifact_gc.py`

### 3.4 任务系统执行器

**执行器核心**（`executor.py`：`TaskExecutor`）：
- 执行单个 `ScheduledTask`
- `spec` 模式：通过 `agent_runtime.create_loop_from_id()` 使用预定义技能
- `prompt` 模式：直接创建 AgentLoop，使用默认模型和系统提示

**执行流程：**
```
1. 创建 AgentLoop（带 checkpoint_fn 持久化消息）
2. 执行 agent.run(task.prompt)
3. 收集元数据：tool_call_count、success_count、duration、model 等
4. 保存报告（Markdown 格式到 reports/scheduled_tasks/）
5. 持久化会话消息到 SessionStore
6. 飞书通知（card 或 text）
7. 可选保存 Markdown 输出
```

**调度器**（`scheduler.py`：`TaskScheduler`）：
- 基于轮询的定时任务调度，check_interval=30s
- 每分钟检查所有任务
- `get_scheduled_minute_key()` 判断当前分钟是否应该执行
- Redis 分布式锁防止重复触发（trigger key + running key）
- 支持漏执行恢复

**防重机制：**
- `acquire_trigger()`：Redis SET NX，TTL=check_interval*4
- `acquire_running()`：Redis SET NX，TTL=600s
- `is_task_running()`：检查 running key

**Cron 调度器**（`cron_scheduler.py`）：
- 基于 `croniter` 库解析 cron 表达式
- 支持时区配置（默认 Asia/Shanghai）

**任务存储**（`store.py`：`TaskStore`）：
- 基于 `TaskConfigStore`（数据库）+ JSON 种子文件
- 数据库为空时从 `config/scheduled_tasks.json` 导入
- asyncio.Lock 保证并发安全

**运行时状态**（`runtime_state.py`：`SchedulerRuntimeState`）：
- `acquire_trigger(task_id, minute_key)`：防止同一分钟重复触发
- `acquire_running(task_id)`：防止同一任务并发执行
- `release_running(task_id)`：执行完成后释放锁

**通知系统**（`card_notify.py`）：
- 飞书卡片通知，三级场景匹配：手动指定 > 工具名自动匹配 > 默认 fallback
- 支持 FeishuClient（app bot，支持回调）和 Webhook（基础投递）
- LLM 格式化卡片变量，meta 数据覆盖 LLM 提取值

**关键代码引用：**
- `backend/core/s07_task_system/executor.py`
- `backend/core/s07_task_system/scheduler.py`
- `backend/core/s07_task_system/cron_scheduler.py`
- `backend/core/s07_task_system/store.py`
- `backend/core/s07_task_system/runtime_state.py`
- `backend/core/s07_task_system/card_notify.py`
- `backend/core/s07_task_system/executor_support.py`

### 3.5 计划收敛机制

计划收敛通过 `ConvergenceMonitor`（`plan_convergence.py`）在每个 PlanExecuteRunner 步骤中注入运行时指令，强制限制单个步骤的工具调用次数。

**收敛阈值**（定义在 `plan_step_prompt.py`）：

| 工具调用次数 | 级别 | 行为 |
|------------|------|------|
| 5 | 系统提醒 | 回顾目标，如果信息足够立即给出结论 |
| 8 | 系统警告 | 必须在接下来 2 次工具调用内完成 |
| 10 | 系统强制 | 最后一次提醒，下一轮必须直接输出结论 |

**注入机制：**
```python
def on_event(self, event: AgentEvent) -> None:
    if event.type == "tool_result":
        self._tool_call_count += 1
        self._queue_due_prompts()
    if event.type == "status_change" and event.data == "thinking":
        self._flush_pending_prompts()
```

- 提示以 `Message(role="user", kind="runtime_guard", ephemeral=True)` 形式注入
- 包装在 `<system_directive>` XML 标签中
- `ephemeral=True` 表示不被持久化到 checkpoint

**步骤注册表隔离：**
- `_build_step_registry()` 为每个步骤创建独立 `ToolRegistry`
- 复制父注册表所有工具
- 移除 TODOUPDATE_TOOL_NAME，重新注册绑定到当前 runner 实例

**关键代码引用：**
- `backend/core/s01_agent_loop/plan_convergence.py`
- `backend/core/s01_agent_loop/plan_step_prompt.py`
- `backend/core/s01_agent_loop/plan_execute_runner_steps.py`

### 3.6 设计亮点

1. **子 Agent 三层隔离模型**：系统提示隔离 + 工具注册表隔离 + 运行时环境隔离，确保子 Agent 无法访问主对话历史或与其他子 Agent 通信。
2. **动态/静态双调度模式**：`StaticDagScheduler` 处理预定义依赖图，`DynamicOrchestrator` 支持波浪式动态任务生成，`SchedulerSwitch` 自动选择。
3. **技能系统双模式注入**：inject 模式将 skill prompt 注入 Zone 2，loop 模式创建独立 AgentLoop，`OnDemandSkillLoader` 按需匹配触发。
4. **上下文压缩三层递进**：L1 大工具结果归档到文件系统，L2 旧消息紧凑化保留标识符，L3 LLM 结构化摘要并生成无损备份，每层都有明确降级策略。
5. **子 Agent 任务队列双层架构**：Redis 提供高性能队列和缓存，`SubAgentTaskStore`（SQLAlchemy）提供持久化状态和租约管理，支持任务复用和并发控制。
6. **计划收敛的事件驱动注入**：`ConvergenceMonitor` 监听 `tool_result` 和 `status_change` 事件，在 LLM thinking 前注入 `runtime_guard` 消息，实现无侵入式步骤级收敛控制。
7. **任务调度的分布式锁设计**：Redis SET NX 实现 trigger 锁和 running 锁，支持多实例部署。
8. **结果契约的自动修复机制**：`coerce_agent_result` 在子 Agent 输出非合法 JSON 时，自动调用 LLM 进行最多 2 次修复，失败则降级为 `unparsed` 状态保留原始输出。

### 3.7 潜在问题

1. **LayeredCompressor L2 效率问题**：`while usage > threshold_l2` 循环每次只处理一个结果，大量大结果时效率低；token 计数不准确可能导致无限循环或过早退出。
2. **SubAgentTaskStore 并发安全**：`claim` 使用 `FOR UPDATE SKIP LOCKED`，但部分读操作（`get_status`、`list_task_ids`）未加锁，并发下可能状态不一致。
3. **TaskQueue 双写一致性**：Redis 缓存和 persistence 之间可能存在状态不一致。
4. **计划收敛阈值硬编码**：5/8/10 次工具调用阈值固定，缺乏基于步骤复杂度的动态调整。
5. **spawn_agent 任务复用隐式依赖**：基于输入数据 SHA256，但工具版本、系统提示等隐式依赖变化时可能复用过期结果。
6. **TokenCounter 中文低估**：`len(text) // 4` 对中文内容（1-2 字符/token）严重低估，可能导致压缩不及时。
7. **SkillMatcher 误匹配**：关键词匹配是简单子字符串匹配（`keyword in text`），缺乏语义相似度匹配。
8. **DynamicOrchestrator 固定值**：`max_waves=4` 和 `max_concurrent=5` 固定，大规模任务可能不足。
9. **PermissionPolicy 正则局限**：`readonly_bash` 基于正则表达式，复杂 shell 命令（如 `bash -c 'echo x > file'`）可能无法正确识别写操作。
10. **ArtifactGC 固定周期**：24 小时固定清理周期，高并发场景可能产生大量临时文件。

---

## 4. 类型系统与适配器层

### 4.1 Pydantic 设计模式

Agent Studio 全量使用 Pydantic v2 `BaseModel` 作为类型基础：

**核心模式：**
1. **统一 BaseModel 继承**：所有领域模型继承 `pydantic.BaseModel` — `AgentConfig`、`Message`、`LLMRequest`、`LLMResponse`、`ProviderConfig`、`Session`、`ToolDefinition` 等
2. **`Field(default_factory=...)` 避免可变默认**：`list[str] = Field(default_factory=list)`、`dict[str, Any] = Field(default_factory=dict)`
3. **`model_validator`/`field_validator` 业务逻辑验证**：
   - `MCPServerConfig`：`@model_validator(mode="after")` 强制传输层约束
   - `AgentSpec`：`@field_validator("id")` 正则匹配 spec ID
   - `SimplePlan`：`@field_validator("tasks", mode="before")` 强制 dict 输入转 list
4. **`model_copy(update=...)` 不可变更新**：`ProviderManager`、 `resilient_adapter.py`、`level1_artifact.py`、`openai_support.py` 均使用此模式
5. **`model_dump()`/`model_dump_json()` 序列化**：工具参数序列化、消息持久化、缓存 hash 计算
6. **`ConfigDict(arbitrary_types_allowed=True)`**：`AgentRuntimeDeps` 持有非序列化运行时对象
7. **`AliasChoices` 灵活反序列化**：`ProviderResponse` 接受 `api_key_preview` 或 `api_key`
8. **`StrEnum` 类型安全枚举**：`AgentCategory`、`ProviderType`

**关键代码引用：**
- `backend/common/types/__init__.py`
- `backend/common/types/agent.py`
- `backend/common/types/llm.py`
- `backend/common/types/message.py`
- `backend/common/types/session.py`
- `backend/common/types/tool.py`
- `backend/common/types/sub_agent.py`
- `backend/common/types/mcp.py`
- `backend/common/types/security.py`

### 4.2 消息类型设计

消息类型系统围绕 `Message` 模型构建，采用分层 Zone 架构：

**核心 Message 模型**（`backend/common/types/message.py`）：
- `role`：`Literal["user", "assistant", "system", "tool"]`
- `content`：文本载荷
- `kind`：`MessageKind` — 语义分类
- `ephemeral`：临时消息，不持久化到历史
- `tool_calls` / `tool_results`：工具交互
- `provider_metadata`：provider 特定数据（thinking blocks、reasoning content）
- `timestamp`：datetime

**MessageKind Zones**（语义分层，优先级排序）：
1. `"user_request"` — 实际用户输入
2. `"summary"` — 压缩对话历史摘要
3. `"runtime_guard"` — 系统注入的护栏（ephemeral，不持久化）
4. `"runtime_context"` — 动态工作区/工具上下文
5. `"skill_context"` — 技能特定注入提示
6. `"memory_context"` — 长期记忆条目

**LLMRequest Zone 字段**（`backend/common/types/llm.py`）：
- `skill_messages`、`memory_messages`、`runtime_messages`、`summary_message`、`recent_messages`、`messages`（legacy 扁平列表，向后兼容）

**Message Zones Adapter**（`backend/adapters/message_zones.py`）：
```python
def request_zone_messages(request: LLMRequest, *, include_system: bool) -> list[Message]:
    dynamic = [
        *request.skill_messages,
        *request.memory_messages,
        *request.runtime_messages,
        *([request.summary_message] if request.summary_message else []),
        *request.recent_messages,
    ]
```
- 系统提示去重（`_with_system_first`）确保系统提示只出现一次且在最前

**Artifacts：**
- `ToolArtifact`：生成文件/图片（kind、path、mime_type、label）
- `FileDiff`：代码变更（path、unified_diff、change_type）

**关键代码引用：**
- `backend/common/types/message.py`
- `backend/common/types/llm.py`
- `backend/adapters/message_zones.py`

### 4.3 LLM 适配器抽象

LLM 适配器层使用清晰的抽象层次支持多 provider：

**基类**（`backend/adapters/base.py`：`LLMAdapter`）：
```python
class LLMAdapter(ABC):
    @abstractmethod
    async def test_connection(self) -> bool: ...
    @abstractmethod
    async def complete(self, request: LLMRequest) -> LLMResponse: ...
    @abstractmethod
    def stream(self, request: LLMRequest) -> AsyncIterator[StreamChunk]: ...
```
- 指数退避重试逻辑
- 可重试错误分类（HTTP 429、500-504、网络错误）

**具体适配器：**
1. **AnthropicAdapter**（`anthropic_adapter.py`）：原生 Anthropic Messages API + SSE 流式，`anthropic_support.py` 构建 payload，`anthropic_stream.py` 解析 SSE
2. **OpenAICompatAdapter**（`openai_adapter.py`）：OpenAI 兼容端点，`openai_support.py` 构建 payload，`openai_streaming.py` 流式解析
3. **OllamaAdapter**（`ollama_adapter.py`）：继承 `OpenAICompatAdapter`，覆盖 URL 构造（`/api/chat`）、payload 格式、响应解析

**Provider 特定支持模块：**
- `anthropic_support.py`：`cache_control` prompt 缓存、tool_use/tool_result 块转换、thinking blocks 元数据
- `openai_support.py`：OpenAI 格式 payload、function calling 转换、`reasoning_content` 元数据、流式 tool call delta 缓冲
- `openai_thinking.py`：Kimi 特定 thinking payload

**工厂模式**（`factory.py`）：
```python
class AdapterFactory:
    @staticmethod
    def create(config: ProviderConfig) -> LLMAdapter:
        match config.provider_type:
            case ProviderType.ANTHROPIC: return AnthropicAdapter(config)
            case ProviderType.OPENAI_COMPAT: return OpenAICompatAdapter(config)
            case ProviderType.OLLAMA: return OllamaAdapter(config)
```

**弹性适配器**（`resilient_adapter.py`）：
- `ResilientLLMAdapter` 包装多个适配器
- 主备候选 + deadline 超时
- `CircuitBreaker` 追踪每 provider 失败，阈值后开路
- 响应标注 `selected_provider` / `fallback_from_provider` 元数据

**Provider 管理**（`provider_manager.py`）：
- `ProviderManager`：异步生命周期管理（增删改查）
- 懒加载 + JSON 配置种子
- 缓存基础适配器和路由适配器

**角色路由**（`role_router.py`）：
- `RoleRouter` 按角色解析 provider（"vision"、"text"、"main"）
- `ProviderConfig.roles` CSV 字符串存储角色映射
- `set_role_default()` 确保角色独占分配

**关键代码引用：**
- `backend/adapters/base.py`
- `backend/adapters/factory.py`
- `backend/adapters/resilient_adapter.py`
- `backend/adapters/provider_manager.py`
- `backend/adapters/provider_routing.py`
- `backend/adapters/role_router.py`
- `backend/adapters/anthropic_adapter.py`
- `backend/adapters/openai_adapter.py`
- `backend/adapters/ollama_adapter.py`
- `backend/adapters/anthropic_support.py`
- `backend/adapters/openai_support.py`
- `backend/adapters/anthropic_stream.py`
- `backend/adapters/openai_streaming.py`

### 4.4 Session 状态模型

Session 状态模型分两层：核心领域模型和 API schema 模型。

**核心领域模型**（`backend/common/types/session.py`）：
```python
SessionStatus = Literal["idle", "running", "paused", "completed", "error"]

class SessionConfig(BaseModel):
    model: str
    provider: str = "anthropic"
    system_prompt: str = ""
    max_tokens: int = 16384
    temperature: float = 0.7

class Session(BaseModel):
    id: str = Field(default_factory=generate_id)
    title: str = ""
    workspace: str = ""
    config: SessionConfig
    messages: list[Message] = Field(default_factory=list)
    created_at: datetime
    status: SessionStatus = "idle"
```

**API Schema 模型**（`backend/schemas/session.py`）：
- `CreateSessionRequest`：创建请求
- `SessionResponse`：响应（含 message_count）

**消息历史**（`message_history.py`）：
- `MessageHistory` 包装原始消息列表，带 checkpoint 持久化
- `checkpoint_fn` 异步持久化每条追加的消息
- `ensure_system_message()` 前置系统提示
- `raw_messages` 暴露可变内部列表供压缩

**Agent Loop 状态**（`agent_loop.py`）：
- `_status`：`AgentStatus`（idle、thinking、tool_calling、waiting_approval、done、error）
- `_history`：`MessageHistory` 实例
- `_handlers`：`AgentEventHandler` 回调列表
- `_aborted`：中止标志
- `_security_gate`：工具授权
- `_compressor` / `_layered_compressor`：上下文压缩管道
- `_skill_loader` / `_memory_index`：技能和记忆注入

**计划状态**（`plan_models.py`）：
- `PlanState`：`PlanPhase` 枚举（IDLE、RECON、PLANNING、EXECUTING 等）
- `ExecutionPlan`：goal、approach、risks、key_files、steps
- `TodoState`：每步运行时进度追踪
- `PlanStep`：dependencies、tools_hint、type

**持久化：**
- `SessionStore`：数据库持久化会话
- `SubAgentTaskStore`：带租约的子 Agent 任务状态持久化
- `MemoryStore`：长期记忆条目持久化

**关键代码引用：**
- `backend/common/types/session.py`
- `backend/schemas/session.py`
- `backend/core/s01_agent_loop/agent_loop.py`
- `backend/core/s01_agent_loop/message_history.py`
- `backend/core/s01_agent_loop/plan_models.py`

### 4.5 设计亮点

1. **Message Zone 架构**：`LLMRequest` 将消息分为语义 zone（skill_messages、memory_messages、runtime_messages、summary_message、recent_messages），支持精确的上下文注入、prompt 缓存稳定性和独立管理。
2. **分层上下文压缩**：三层压缩系统（L1 artifact 下沉、L2 旧工具摘要紧凑化、L3 LLM 结构化摘要并归档），渐进式减少上下文大小，信息永不丢失。
3. **Provider 抽象与弹性**：`LLMAdapter` ABC + `AdapterFactory` 支持 Anthropic、OpenAI 兼容、Ollama。`ResilientLLMAdapter` 添加断路器自动回退。
4. **Prompt Cache 前缀稳定性**：`build_cache_prefix_hash()` 计算 system_prompt + tools schema 的 SHA-256 hash 作为缓存键，确保稳定前缀可缓存。
5. **Skill 注入上下文系统**：`AgentRuntime` 组合分层提示（stable base + spec-specific），skill 消息以 `kind="skill_context"` 注入，`OnDemandSkillLoader` 基于用户输入关键词匹配。
6. **安全门控工具执行**：`SecurityPolicy` + `SecurityGate` + `SignedToolCall` 三层授权，工具按权限分类，调用 HMAC 签名，执行前验证签名。
7. **子 Agent 任务队列去重**：`spawn_agent` 使用基于内容 SHA-256 hash 的 `TaskQueue` 去重，已完成任务可复用，通过 `SubAgentPolicy` 限制派发容量。
8. **计划执行状态机**：`PlanState` + `PlanPhase` 枚举建模完整计划生命周期，每阶段转换持久化且可恢复。
9. **事件驱动架构**：`AgentEvent`/`AgentEventHandler` 解耦 Agent 循环与所有传输层，同一循环可驱动 WebSocket、飞书、CLI、定时任务。
10. **类型安全错误层次**：`AgentError`（基类）→ `ToolError`/`LLMError`，所有错误携带结构化 code（"RATE_LIMIT"、"AUTH_ERROR"、"CONTEXT_COMPRESSION_FAILED"）。

### 4.6 潜在问题

1. **Schema 重复**：`AgentConfig`（`common/types/agent.py`）和 `SessionConfig`（`common/types/session.py`）字段几乎相同（model、provider、system_prompt、max_tokens、temperature），可能导致漂移。
2. **Message Zone Legacy Fallback**：`request_zone_messages()` 在动态 zone 为空时回退到 `request.messages`，部分代码路径使用 zone，部分使用扁平 legacy 列表。
3. **ProviderConfig.roles 为 CSV 字符串**：每次访问需解析/分割，缺乏类型安全。
4. **OllamaAdapter 继承 OpenAICompatAdapter**：Ollama API 与 OpenAI 差异显著，当前覆盖方式可能脆弱。
5. **TokenCounter 启发式精度**：`len(text) // 4` 对非英文文本不准确，大上下文窗口下可能导致过早或延迟压缩。
6. **Summary Message 角色语义模糊**：Summary 消息使用 `role="user"` 但 `kind="summary"`，语义上不是用户输入。
7. **AgentSpec.mode 字段重载**：`mode` 字段为 `"inject"`/`"loop"`，`default_mode` 为 `"direct"`/`"plan_execute"`，两个 "mode" 语义不同。
8. **Circuit Breaker 非持久化**：状态仅内存存储，进程重启后失败计数重置。
9. **MemoryIndex 评分简单**：`_score()` 仅简单关键词匹配 + hit_count 加成，无 embedding 或语义相似度。
10. **工具输出截断盲目**：`_truncate_output()` 在字符边界截断，不尊重 token 边界或语义单元，JSON 输出可能截断为非法 JSON。

---

## 5. 业界设计模式对比

### 5.1 ReAct 模式

**核心思想**：交错推理与行动（Thought → Action → Observation），将推理锚定在外部可验证的观察上。

**演进路线**：
- ReAct (2022)：线性循环
- Reflexion (2023)：增加语言强化学习，失败反思存入情景记忆
- LATS (2023)：扩展为蒙特卡洛树搜索（MCTS）

**Agent Studio 现状：**
- `AgentLoop.run_agent_loop()` 实现了完整的 ReAct 循环（LLM 调用 → 解析 tool_calls → 并行执行只读工具 → 串行执行写工具 → 结果回写 → 下一轮）
- `ConvergenceMonitor` 防止无限循环
- `ToolFailureRecoveryTracker` 实现重复失败检测和恢复提示注入
- `LayeredCompressor` 管理长上下文防止溢出

**缺失：**
1. **Reflexion 的记忆机制**：无跨会话的 episodic memory 存储失败反思
2. **LATS 的树搜索**：无 MCTS 或任何树形探索机制
3. **价值评估函数**：无评估中间状态价值的机制

### 5.2 Plan-and-Execute

**核心思想**：先分解、后执行的两阶段策略。

**演进路线**：
- Plan-and-Solve (2023)："Let's first devise a plan" + "Let's carry out the plan"
- HuggingGPT (2023)：LLM 作为控制器，负责任务分解、模型选择、依赖管理
- ProgPrompt：将自然语言任务转化为代码生成

**Agent Studio 现状（非常完善）：**
- `PlanExecuteRunner` 实现完整 Plan-and-Execute 流程
- 状态机：`PlanState` + `PlanPhase`（IDLE → RECON → PLANNING → PLAN_READY → EXECUTING → COMPLETED）
- 计划模型：`ExecutionPlan` 包含 goal、approach、risks、key_files、steps
- 步骤执行：每步独立 `AgentLoop`，带隔离 session_id 和工具注册表
- 暂停/恢复：`PlanControlState` 支持运行中暂停和恢复
- 确认机制：`require_confirmation` 允许用户执行前审查计划
- 收敛监控：`ConvergenceMonitor` 防止步骤无限循环

**缺失：**
1. **动态计划调整**：计划一旦生成，执行过程中无法根据中间结果调整
2. **依赖感知并行**：步骤间虽有 `depends_on`，但执行是顺序的，未利用 DAG 并行化
3. **计划质量评估**：生成计划后无评估可行性的机制

### 5.3 Self-Reflection

**三层自我修正架构：**

| 方法 | 层级 | 机制 | 记忆 |
|------|------|------|------|
| Self-Refine (2023) | 单次生成内 | Generator → Critic → Refiner | 无 |
| Reflexion (2023) | 完整任务尝试 | Actor + Evaluator + Self-Reflection | Episodic memory |
| CRITIC (2023) | 子任务/验证点 | 结合外部工具验证 | 无 |

**关键洞察**：内在修正（仅依赖模型自身）可靠性低；接地修正（锚定在工具输出）可靠性高。

**Agent Studio 现状：**
- `ToolFailureRecoveryTracker`：检测重复失败并注入恢复提示
- `ConvergenceMonitor`：tool_call 数量阈值处注入收敛提示
- `AgentLoopApprovalMixin`：工具审批机制
- `SecurityGate`：工具调用权限校验

**缺失：**
1. **结构化自我反思**：无 Generator-Critic-Refiner 三角色分离
2. **接地验证**：无系统性工具辅助验证流程（CRITIC 模式）
3. **PRM 集成**：无过程奖励模型或步骤级评分
4. **跨会话学习**：Reflexion 的情景记忆未实现

### 5.4 层次化 Agent

**核心思想**：模仿人类组织结构，通过控制层级分解复杂性。

**主要模式：**

| 模式 | 结构 | 控制方式 | 典型框架 |
|------|------|---------|---------|
| Supervisor-Worker | 主管 + 多个工作者 | 任务分解、路由、聚合 | LangGraph、CrewAI |
| Manager-Executor | 经理设定子目标 | 时间尺度分离 | Feudal HRL |
| 三层次结构 | 战略 → 规划 → 执行 | 不同时间粒度 | MAS-H² |

**Agent Studio 现状：**
- `spawn_agent`：支持并行派生子 Agent，带任务队列和结果聚合
- `Orchestrator`（`static_dag.py`）：静态 DAG 执行，按阶段解析依赖，同阶段并行
- `DynamicOrchestrator`：动态多波次执行，`DynamicPlanner` 协议
- `run_isolated_agent`：隔离子 Agent 执行，带权限控制

**缺失（关键）：**
1. **s09_agent_teams 完全为空**：team_coordinator、role_assigner、quality_gate、handoff_manager 未实现
2. **s10_team_protocol 完全为空**：message_bus、shared_state、conflict_resolver 未实现
3. **s11_autonomous_agent 完全为空**：decision_engine、goal_decomposer、feedback_collector 未实现
4. **无 Supervisor 角色**：现有 `Orchestrator` 是执行编排器，非智能主管
5. **无 Agent 间通信协议**：子 Agent 完全隔离，无消息总线或共享状态

### 5.5 工具增强 Agent

**演进路线**：GPT-3 → WebGPT → ToolFormer → Gorilla → Function Calling APIs → Agentic Tool Use

**生产架构模式（2025-2026）：**
1. 分层工具选择：两阶段路由（语义路由层先筛选候选工具）
2. DAG 并行执行：模型生成带显式依赖声明的工具调用 DAG
3. 分层错误处理：验证门 → 断路器 → 幂等工作流 + Saga 回滚 → 人工升级
4. 语义缓存：消除冗余工具调用
5. OpenTelemetry 可观测性：每工具 span

**Agent Studio 现状（非常完善）：**
- `ToolRegistry`：工具注册、查询、schema 管理
- `ToolExecutor`：批量并行执行、签名验证、输出截断
- 副作用感知批处理：`partition_by_side_effect` 读写分离
- 安全门控：`SecurityGate` HMAC 签名 + 权限校验
- MCP 集成：`MCPToolBridge` + `MCPServerManager`
- 丰富内置工具集：20+ 工具
- 工具审批：危险操作人工确认

**缺失：**
1. **分层工具选择**：所有工具一次性注入 LLM prompt，工具数量增加时准确率下降
2. **DAG 并行**：仅读写分离，无真正的依赖感知并行调度
3. **语义缓存**：无工具调用结果缓存
4. **高级错误处理**：无断路器、Saga 回滚
5. **可观测性**：无 OpenTelemetry 标准的 per-tool 观测

### 5.6 Agent Studio 缺失的能力

按优先级排序：

1. **s09_agent_teams 模块完全为空** — 团队协调、角色分配、质量门控、交接管理
2. **s10_team_protocol 模块完全为空** — 消息总线、共享状态、冲突解决
3. **s11_autonomous_agent 模块完全为空** — 自主决策引擎、目标分解器、反馈收集器、学习适配器
4. **Reflexion 的 episodic memory** — 跨会话学习失败经验
5. **LATS 的树搜索和价值评估** — MCTS 探索机制
6. **结构化自我反思** — Generator-Critic-Refiner 三角色分离
7. **Process Reward Model (PRM)** — 步骤级评分
8. **分层工具选择/路由** — 两阶段工具路由
9. **工具调用语义缓存** — 基于参数 hash 的结果缓存
10. **DAG 感知的依赖并行调度** — 超越读写分离的并行
11. **动态计划重规划** — Plan-Execute 计划生成后不可调整
12. **Supervisor 智能路由和负载均衡** — 动态任务分配
13. **Agent 间通信协议和共享状态** — 超越完全隔离
14. **断路器和 Saga 回滚** — 高级错误处理
15. **OpenTelemetry 兼容的 per-tool 可观测性** — 标准化观测

---

## 6. 路由层最佳实践对比

### 6.1 FastAPI 高级模式

**最佳实践：**
- 依赖注入（`Depends()`）解耦横切关注点
- 背景任务（`BackgroundTasks`）处理非阻塞后台操作
- Lifespan 管理（`@asynccontextmanager`）统一重型资源生命周期
- 中间件链处理追踪、CORS、认证、错误处理、速率限制

**Agent Studio 现状：**
- 已使用 `@asynccontextmanager`（`app.py:28-126`）
- 中间件链已建立：`RequestTraceMiddleware` → `CORS` → 路由（`app.py:148-155`）
- 认证中间件使用 `secrets.compare_digest`（`auth.py`）
- 请求追踪实现 trace_id 传播和 Prometheus 指标（`request_trace.py`）

**差距：**
1. **依赖注入不足**：大多数路由直接从 `app.state` 获取资源，而非 `Depends()` 注入
2. **无速率限制**：`rate_limit.py` 为空文件
3. **Lifespan 臃肿**：`_lifespan` 函数 98 行，包含 6+ 初始化职责
4. **无请求体验证中间件**：无统一请求体大小限制
5. **错误处理分散**：每个路由重复 try-except，`error_handler.py` 为空
6. **背景任务缺失**：飞书消息处理使用 `asyncio.create_task()` 而非 `BackgroundTasks`

### 6.2 WebSocket 设计

**最佳实践：**
- 连接管理：`Set[WebSocketServerProtocol]` 或字典跟踪活跃连接
- 心跳机制：协议级（`ping_interval`/`ping_timeout`）+ 应用级双模式
- 广播模式：`websockets.broadcast()` 避免背压
- 连接隔离：每会话独立管理
- 优雅断开：捕获 `WebSocketDisconnect` 和 `asyncio.CancelledError`

**Agent Studio 现状：**
- `ConnectionManager` 使用字典管理连接、loop、plan runner、subscriber task（`websocket.py:33-127`）
- Redis pub/sub 跨 worker 广播（`websocket_pubsub.py`）
- 断开时清理 subscriber task 和连接（`websocket.py:48-70`）
- 支持 session 级别消息同步到数据库

**差距：**
1. **无心跳机制**：无 `ping_interval` 或应用级心跳
2. **广播实现问题**：逐个连接发送，未使用 `websockets.broadcast()`
3. **无连接超时检测**：无长时间无活动检测
4. **消息循环过大**：`ws_endpoint` 243 行，处理 10+ 种消息类型
5. **无连接数限制**
6. **无连接认证**
7. **subscriber task 异常处理弱**

### 6.3 消息队列集成

**最佳实践：**
- 任务队列 vs 事件流：Redis List + BRPOP 适合工作分配，Redis Streams/Kafka 适合事件溯源
- 至少一次交付：幂等消费者 + 去重
- 租约机制：任务 claim 后设置过期时间
- 心跳续约：worker 定期续约
- 死信队列：失败任务超过重试次数后转入 DLQ

**Agent Studio 现状：**
- 基于 Redis List + BRPOP 的任务队列（`task_queue.py`）
- 完整生命周期：claim、complete、fail、lease renew
- 子 Agent consumer 心跳（`task_queue_consumer.py:65-68`，15 秒间隔）
- Redis + PostgreSQL 双层存储
- stale task 恢复机制

**差距：**
1. **使用 Redis List 而非 Streams**：缺少消费者组、消息重放、偏移量管理
2. **无死信队列**：失败任务直接标记 FAILED
3. **无任务优先级**：所有任务 FIFO
4. **无消息去重**：除飞书事件外，任务队列本身无去重
5. **BRPOP 阻塞时间固定**
6. **无队列深度监控**
7. **任务结果无回调机制**

### 6.4 Webhook 处理

**最佳实践：**
- HMAC-SHA256 签名验证 + 常数时间比较
- 时间戳验证（拒绝 >300 秒请求）
- 异步处理：立即返回 200 OK，后台处理
- 事件去重：Redis SETNX 或幂等键
- 事件分发：EventDispatcher 模式
- 错误隔离：单个处理器失败不影响其他事件

**Agent Studio 现状：**
- HMAC-SHA256 签名验证（`feishu_signature.py`）
- `FeishuEventDispatcher` 分发事件（`feishu_events.py:20-38`）
- 飞书事件去重（`feishu_runtime.py:128-166`），Redis SETNX + 5 分钟 TTL
- 加密 payload 解密支持（`feishu_events.py:102-106`）
- 消息处理异步化（`feishu.py:134`）

**差距：**
1. **两个飞书事件路由重复**：`/feishu/events` 和 `/api/feishu/event`
2. **无时间戳验证**：存在重放攻击风险
3. **事件处理器过于庞大**：`FeishuMessageHandler.handle_message` 138 行
4. **无事件重试机制**
5. **无 webhook 日志**
6. **卡片操作 fallback 脆弱**
7. **无 webhook 限流**

### 6.5 Streaming 响应

**最佳实践：**
- SSE：`text/event-stream` 格式，`data: {...}\n\n`
- 关键响应头：`X-Accel-Buffering: no`、`Cache-Control: no-cache`、`Connection: keep-alive`
- 客户端断开检测：`request.is_disconnected()`
- 心跳保活：`: ping\n\n`
- 错误处理：流中错误时发送错误事件后正常结束

**Agent Studio 现状：**
- OpenAI 兼容 SSE 流式响应（`chat_completions.py:136-167`）
- `asyncio.Queue` 桥接异步事件和流式生成器
- 支持 tool call 和 tool result 流式输出
- WebSocket 实时消息推送

**差距：**
1. **缺少关键响应头**：无 `X-Accel-Buffering: no`
2. **无客户端断开检测**：`event_generator` 未检查 `raw_request.is_disconnected()`
3. **无心跳保活**
4. **Queue 超时过短**：`asyncio.wait_for(queue.get(), timeout=0.1)` 每 100ms 超时，CPU 空转
5. **缺少流式错误事件格式**
6. **无流式指标**
7. **WebSocket 流式无背压控制**
8. **缺少流式取消传播**：客户端断开时底层 LLM 请求未取消

### 6.6 与最佳实践的差距

| 差距项 | 严重程度 | 说明 |
|--------|---------|------|
| 依赖注入严重不足 | 高 | 路由直接访问 `app.state`，测试困难 |
| 速率限制完全缺失 | 高 | `rate_limit.py` 为空，LLM 端点无保护 |
| WebSocket 无心跳 | 高 | 代理环境下易超时断开 |
| 消息队列使用 List 非 Streams | 中 | 缺少消费者组、消息重放 |
| 两个飞书 webhook 路由重复 | 中 | 维护成本高 |
| Lifespan 函数臃肿 | 中 | 98 行，6+ 职责 |
| SSE 缺少关键头 | 中 | nginx 下可能被缓冲 |
| 无全局异常处理 | 中 | `error_handler.py` 为空 |
| 文件大小无限制 | 中 | 知识库上传端点无限制 |
| WebSocket 无认证 | 高 | 任何客户端可连接 |
| 缺少 API 版本控制 | 低 | 不利于 API 演进 |
| 无死信队列 | 中 | 失败任务无后续分析 |
| 飞书 webhook 无时间戳验证 | 高 | 重放攻击风险 |
| 代码文件过大 | 中 | `feishu_handler.py` 512 行、`websocket.py` 431 行 |
| 无队列深度监控 | 低 | 缺少告警和自动扩缩容依据 |

---

## 7. 上下文与状态管理对比

### 7.1 上下文窗口管理

Agent Studio 实现了业界较为领先的三层上下文压缩策略：

| 特性 | Agent Studio | MemGPT | LangChain Compressor | Claude Context API |
|------|-------------|--------|---------------------|-------------------|
| 分层压缩 | 3层 (Artifact/Compact/Summary) | 分层记忆 (core/working/external) | 简单滑动窗口 | 无内置 |
| 结构化摘要 | XML 格式，P1-P6 优先级 | 无 | 无 | 无 |
| Token 估算 | 粗略字符/4 | 使用 tiktoken | 使用 tiktoken | 原生准确 |
| 增量压缩 | 否 | 是 | 否 | N/A |
| 降级策略 | 有 fallback | 无 | 无 | N/A |
| 归档到文件 | 是 | 否 | 否 | 否 |

**关键问题：**
- `TokenCounter` 使用 `len(text)//4`，中文内容 1 token ~ 1-2 字符，混合内容估算误差可达 50-100%
- `threshold_l2=0.5` 在 180K 上下文下 90K 就开始 L2 压缩，触发过早
- 无增量摘要机制，每次重新摘要全部旧消息
- 无 prompt caching 优化（虽然计算了 `cache_prefix_hash`）
- `max_context_tokens=180000` 固定，对 GPT-4 (128K) 会溢出

### 7.2 状态持久化

**检查点机制：**
- `MessageHistory`：支持可选 `checkpoint_fn`，逐条消息触发；`checkpoint_failed` 标志不阻塞主流程
- `PlanCheckpointStore`：原子写（tmp → bak → replace），支持 `.bak` 回滚
- `PlanResume`：支持从任意非终端状态恢复，`_reset_interrupted_steps` 将 running 重置为 pending

**持久化层评估：**

| 维度 | 评分 | 说明 |
|------|------|------|
| PostgreSQL 使用 | 7/10 | 分工清晰，连接池配置合理，但 JSON 字段用 Text 存储无法索引 |
| Redis 使用 | 6/10 | 队列/缓存分工清晰，但无 Sentinel/Cluster，单点故障 |
| 检查点设计 | 8/10 | 原子写 + 回滚机制良好 |
| 分布式一致性 | 5/10 | Redis 和 PostgreSQL 无分布式事务 |

**关键问题：**
- `MessageRecord` 的 `tool_calls_json`、`tool_results_json` 使用 Text 类型存储，无法索引和查询
- 无消息内容全文索引
- 无按时间范围的分区表
- `PlanControlStore` 基于文件系统，分布式部署时无法共享控制信号
- 子任务无 checkpoint 机制，失败后从头重试

### 7.3 记忆系统

| 特性 | Agent Studio | MemGPT | AutoGPT | 理想方案 |
|------|-------------|--------|---------|---------|
| 短期记忆 | 内存列表 | 分层 (core/working) | 内存列表 | 内存 + 滑动窗口 |
| 长期记忆 | 文件 JSON + 关键词 | 向量 DB + 召回 | 向量 DB | 向量 DB + 分层索引 |
| 语义检索 | 无 | 有 (embedding) | 有 | 有 |
| 记忆写入 | 手动/文件 | 自动提取 | 半自动 | 自动提取 + 审核 |
| 记忆衰减 | 无 | 有 | 无 | 有 |
| Episodic | 间接 (step result) | 有 | 有 | 有 |

**关键问题：**
- `LongTermMemory` 纯文件存储（`data/memory/experiences.json`），无并发控制
- `MemoryIndex` 仅关键词匹配（`keyword in text`），无向量检索
- 无语义相似度计算
- 无记忆衰减/遗忘机制
- 所有记忆加载到内存，无法扩展
- `hit_count` 权重太低（最大 0.2）
- 无从 episodic 记录提取通用经验写入长期记忆的机制

### 7.4 消息路由

**Message Zones 设计**（`message_zones.py`）：
```python
dynamic = [
    *request.skill_messages,      # Zone 2
    *request.memory_messages,     # Zone 3
    *request.runtime_messages,    # Zone 4
    *([request.summary_message] if request.summary_message else []),  # Zone 5
    *request.recent_messages,     # Zone 6
]
```

**评分：7/10**

**合理之处：**
- 消息分区概念清晰
- 与 `LLMRequest` 模型配合良好
- 便于 adapter 层做 prompt caching 优化

**不合理之处：**
- 无优先级队列：紧急消息（用户打断）无优先处理
- 无消息分片：大消息（长代码文件）无分片机制
- Zone 顺序固定：无根据场景动态调整能力
- 无消息去重：相同内容可能重复注入
- `ephemeral` 标记未在 routing 中使用
- `legacy_messages` 和分区消息并存，有重复风险

### 7.5 多轮对话状态

**Plan Phase 状态机**（`plan_state_machine.py`）：
```
IDLE → RECON → PLANNING → PLAN_READY → [CONFIRMING/AWAITING_APPROVAL] → EXECUTING → [COMPLETED/PARTIAL_FAILED/PAUSED]
```

**意图保持：**
- `AgentLoopGuard`：`dead_end_reflection_iteration` 注入反思提示，`final_convergence_prompt` 注入收口提示
- `ConvergenceMonitor`：按工具调用次数（5/8/10）注入收敛提示

**上下文切换：**
- Plan Step：每步独立 AgentLoop 和 session_id，通过 `previous_summary` 和 `completed_context` 传递状态
- Sub-agent：`run_isolated_agent` 完全隔离，通过 `dependency_outputs` 显式传递依赖结果

**Session 管理：**
- `SessionStore`：CRUD 完整，消息按 timestamp + id 排序
- `save_messages` 全量替换（先 delete 再 insert）

**与行业对比：**

| 特性 | Agent Studio | Coze/扣子 | Dify | LangGraph |
|------|-------------|----------|------|-----------|
| 状态机 | 有 (Plan) | 有 | 有 | 有 (图) |
| 意图保持 | 弱 (prompt-based) | 中 | 中 | 强 (状态节点) |
| 上下文切换 | 强隔离 | 中 | 中 | 强 (checkpoint) |
| 多轮恢复 | 有 (checkpoint) | 有 | 有 | 有 |
| 用户打断 | 有 (pause/stop) | 有 | 有 | 有 |

**关键问题：**
- 意图保持主要靠 system prompt，无显式意图栈
- 用户中途插入新任务时，无意图切换/保存机制
- 上下文切换成本高（每次新建 AgentLoop）
- 无上下文预热（prompt cache warming）
- `SessionStore.save_messages` 全量替换效率低

### 7.6 Agent Studio 的行业定位

**s06_context_compression 定位：**
- 架构设计处于行业前 20%，实现质量处于行业中游（50%）
- 概念先进（三层递进 + 结构化摘要 + P1-P6 优先级）但工程化不足（token 估算不准、压缩触发过早、无增量机制）

**子 Agent 上下文隔离定位：**
- 评分 8.5/10
- 强隔离、权限控制、工具白名单、依赖注入、结果归档、任务去重均为亮点
- 缺少子 Agent 间通信、独立上下文压缩策略、结果缓存

**持久化层定位：**
- 评分 7/10
- 分工清晰、连接池合理、租约机制、原子写设计良好
- JSON 字段 Text 存储、无分布式事务、无消息分区表、Redis 单点

---

## 8. 架构缺口分析

按优先级排序的缺失能力清单：

### P0 - 阻塞性缺口（影响生产安全）

| # | 缺口 | 影响 | 相关文件 |
|---|------|------|---------|
| 1 | 速率限制完全缺失 | LLM API 滥用导致成本失控 | `rate_limit.py`（空） |
| 2 | WebSocket 无认证 | 任何客户端可连接，安全漏洞 | `websocket.py` |
| 3 | 飞书 webhook 无时间戳验证 | 重放攻击风险 | `feishu_signature.py` |
| 4 | Token 计数严重不准 | 中文场景压缩不及时，上下文溢出 | `token_counter.py` |
| 5 | 无全局异常处理 | 每个路由重复 try-except，维护困难 | `error_handler.py`（空） |

### P1 - 高优先级缺口（影响核心能力）

| # | 缺口 | 影响 | 相关文件/模块 |
|---|------|------|--------------|
| 6 | s09_agent_teams 完全为空 | 无团队协调、角色分配、质量门控 | `backend/core/s09_agent_teams/` |
| 7 | s10_team_protocol 完全为空 | 无 Agent 间通信协议和共享状态 | `backend/core/s10_team_protocol/` |
| 8 | s11_autonomous_agent 完全为空 | 无自主决策、目标分解、学习适配 | `backend/core/s11_autonomous_agent/` |
| 9 | 长期记忆使用文件 JSON + 关键词匹配 | 无法扩展，召回质量差 | `memory_index.py`、`long_term_memory.py` |
| 10 | MessageRecord JSON 字段 Text 存储 | 无法索引和查询 | `storage/session_store.py` |
| 11 | 无分层工具选择/路由 | 工具数量增加时准确率急剧下降 | `tool_registry.py` |
| 12 | 无动态计划重规划 | Plan-Execute 计划生成后不可调整 | `plan_execute_runner.py` |
| 13 | 依赖注入严重不足 | 代码耦合度高、测试困难 | 所有路由文件 |

### P2 - 中优先级缺口（影响工程质量和扩展性）

| # | 缺口 | 影响 | 相关文件 |
|---|------|------|---------|
| 14 | 消息队列使用 Redis List 非 Streams | 缺少消费者组、消息重放 | `task_queue.py` |
| 15 | 无死信队列 | 失败任务无后续分析 | `task_queue.py` |
| 16 | WebSocket 无心跳机制 | 代理环境下易超时断开 | `websocket.py` |
| 17 | 两个飞书 webhook 路由重复 | 维护成本高 | `feishu.py`、`feishu_events.py` |
| 18 | Lifespan 函数臃肿 | 98 行，6+ 职责 | `app.py` |
| 19 | SSE 缺少关键响应头 | nginx 下可能被缓冲 | `chat_completions.py` |
| 20 | 代码文件过大 | 违反 200 行约束 | `feishu_handler.py` (512)、`websocket.py` (431) |
| 21 | 无工具调用语义缓存 | 冗余调用浪费计算 | `executor.py` |
| 22 | 无断路器和 Saga 回滚 | 高级错误处理缺失 | `executor.py` |
| 23 | PlanControlStore 文件存储 | 分布式部署无法共享 | `plan_control_store.py` |

### P3 - 低优先级缺口（优化项）

| # | 缺口 | 影响 | 相关文件 |
|---|------|------|---------|
| 24 | 无 API 版本控制 | 不利于 API 演进 | `app.py` |
| 25 | 无 OpenTelemetry 兼容观测 | 标准化观测缺失 | 所有适配器 |
| 26 | 无消息优先级队列 | 紧急消息无法优先处理 | `message_zones.py` |
| 27 | 无大消息分片 | 超长代码文件可能占满上下文 | `message_zones.py` |
| 28 | Redis 无 Sentinel/Cluster | 单点故障风险 | `config/settings.py` |
| 29 | 无 prompt caching 优化 | 重复摘要成本高 | `anthropic_adapter.py` |
| 30 | Circuit Breaker 非持久化 | 进程重启后状态重置 | `resilient_adapter.py` |

---

## 9. 改进路线图

### 9.1 短期（1-2 周）

1. **实现全局异常处理中间件**（`error_handler.py`）
   - 创建 `ExceptionMiddleware` 统一捕获未处理异常
   - 统一错误响应格式 `{"code": "...", "message": "..."}`
   - 将现有路由的重复 try-except 逐步迁移

2. **实现基于 Redis 的滑动窗口速率限制**（`rate_limit.py`）
   - LLM 端点：60 RPM / 用户
   - 普通端点：1000 RPM / 用户
   - 飞书 webhook：100 RPM / chat_id

3. **修复 Token 计数**（`token_counter.py`）
   - 引入 `tiktoken`（OpenAI）或 anthropic tokenizer
   - 按 provider 选择对应 tokenizer
   - 中文场景误差从 50-100% 降至 <5%

4. **添加 WebSocket 认证**
   - 握手时验证 `Authorization` header 或 query param 中的 token
   - 未认证连接立即关闭

5. **添加飞书 webhook 时间戳验证**
   - 在签名验证中添加时间戳检查
   - 拒绝超过 300 秒的请求

6. **拆分臃肿文件**
   - `feishu_handler.py` → `feishu_message_handler.py`、`feishu_menu_handler.py`、`feishu_plan_handler.py`
   - `websocket.py` → 消息路由器、连接管理器、消息处理器

### 9.2 中期（1-2 月）

1. **重构依赖注入层**（`backend/api/deps.py`）
   - 创建 `get_session_store()`、`get_task_queue()`、`get_agent_runtime()` 等依赖工厂
   - 通过 `Depends()` 注入到所有路由
   - 移除 `getattr(request.app.state, ...)` 模式

2. **迁移长期记忆到 pgvector**
   - 利用已安装的 PostgreSQL pgvector 扩展
   - 为 `MemoryEntry` 添加 embedding 字段
   - 实现语义相似度检索替代关键词匹配
   - 保留关键词匹配作为回退

3. **实现分层工具选择**（`ToolRouter`）
   - 在 `ToolRegistry` 和 `AgentLoop` 之间增加 `ToolRouter`
   - 两阶段路由：先语义匹配筛选候选工具子集（5-10 个），再注入 LLM
   - 与现有 `ToolRegistry` 兼容

4. **升级任务队列为 Redis Streams**
   - 使用 Redis Streams 替代 List
   - 支持消费者组、消息重放、偏移量管理
   - 实现死信队列（DLQ）

5. **实现动态计划重规划**（`PlanExecuteRunner`）
   - 增加 `replan()` 方法
   - 步骤失败或结果偏差大时触发重新规划剩余步骤
   - 利用现有 `PlanState` 状态机管理重规划流程

6. **添加 WebSocket 心跳和背压控制**
   - 应用级心跳：每 30 秒 ping，10 秒超时
   - 背压控制：客户端缓冲区满时暂停发送
   - 客户端断开检测和取消传播

7. **MessageRecord 字段类型优化**
   - `tool_calls_json`、`tool_results_json` 从 Text 改为 JSONB
   - 添加消息内容全文索引
   - 按时间分区 MessageRecord 表

8. **合并飞书事件路由**
   - 将 `/feishu/events` 和 `/api/feishu/event` 合并为单一入口
   - 统一签名验证和事件分发逻辑

### 9.3 长期（3-6 月）

1. **实现 s09_agent_teams**
   - `TeamCoordinator`：管理团队生命周期和任务分配
   - `RoleAssigner`：根据任务特征动态分配角色
   - `QualityGate`：子 Agent 输出质量检查
   - `HandoffManager`：Agent 间控制转移

2. **实现 s10_team_protocol**
   - `MessageBus`：异步消息传递，支持 pub/sub 和点对点
   - `SharedState`：跨 Agent 共享状态变量
   - `ConflictResolver`：多 Agent 输出冲突时的仲裁

3. **实现 s11_autonomous_agent**
   - `DecisionEngine`：自主决策引擎
   - `GoalDecomposer`：目标分解器
   - `FeedbackCollector`：反馈收集器
   - `LearningAdapter`：学习适配器

4. **引入 Reflexion 记忆机制**
   - 扩展 `MemoryIndex` 或新增 `ReflectionStore`
   - 按 `(task_pattern, error_type)` 索引反思摘要
   - 支持跨会话检索

5. **实现工具调用语义缓存**（`ToolResultCache`）
   - 基于调用参数 hash 缓存结果
   - 支持 TTL 和失效策略
   - 减少冗余调用

6. **增强可观测性**
   - 扩展现有 trace_span，增加 OpenTelemetry 兼容的 per-tool span
   - 捕获 latency、success_rate、schema_violation 等指标
   - 队列深度、任务处理延迟、失败率暴露到 Prometheus

7. **实现 DAG 感知的依赖并行调度**
   - 超越读写分离，真正的依赖感知并行
   - 利用 `PlanStep.depends_on` 构建 DAG
   - 拓扑排序确定可并行执行的步骤组

8. **迁移 PlanControlStore 到 Redis**
   - 将文件系统存储改为 Redis
   - 支持分布式部署共享控制信号

9. **添加 Redis Sentinel/Cluster 支持**
   - 高可用配置
   - 消除单点故障风险

10. **实现增量上下文压缩**
    - 类似 MemGPT 的递归摘要
    - 每次只压缩新增部分，降低 LLM 调用成本

---

## 10. 代码级重构建议

### 具体到文件/函数级别的建议

#### `backend/core/s06_context_compression/token_counter.py`
```python
# 当前（问题：中文严重低估）
def count_tokens(text: str) -> int:
    return len(text) // 4

# 建议：按 provider 选择 tokenizer
import tiktoken
from anthropic import Anthropic

def count_tokens(text: str, provider: str = "openai", model: str = "gpt-4") -> int:
    if provider == "openai":
        enc = tiktoken.encoding_for_model(model)
        return len(enc.encode(text))
    elif provider == "anthropic":
        # 使用 anthropic token counting API 或近似
        return len(text) // 3  # 更保守的估算
    return len(text) // 3
```

#### `backend/api/middleware/error_handler.py`（当前为空）
```python
from starlette.middleware.base import BaseHTTPMiddleware
from fastapi import Request

class ExceptionMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        try:
            return await call_next(request)
        except AgentError as e:
            return JSONResponse(
                status_code=e.status_code or 500,
                content={"code": e.code, "message": str(e)}
            )
        except Exception as e:
            logger.exception("Unhandled exception")
            return JSONResponse(
                status_code=500,
                content={"code": "INTERNAL_ERROR", "message": "Internal server error"}
            )
```

#### `backend/api/middleware/rate_limit.py`（当前为空）
```python
from fastapi import Request, HTTPException
import redis.asyncio as redis

class RateLimitMiddleware:
    def __init__(self, redis_client: redis.Redis, default_limit: int = 100, window: int = 60):
        self.redis = redis_client
        self.default_limit = default_limit
        self.window = window
    
    async def check(self, request: Request, key: str, limit: int | None = None) -> bool:
        # 滑动窗口计数
        ...
```

#### `backend/api/routes/websocket.py`（243 行 → 拆分）
建议拆分为：
- `websocket.py`（~80 行）：端点定义、连接管理器引用
- `websocket_handler.py`（~120 行）：消息路由分发
- `websocket_handlers/run_handler.py`（~40 行）：run 消息处理
- `websocket_handlers/plan_handler.py`（~40 行）：plan 消息处理
- `websocket_handlers/approval_handler.py`（~30 行）：审批消息处理

#### `backend/api/routes/feishu_handler.py`（512 行 → 拆分）
建议拆分为：
- `feishu_handler.py`（~80 行）：主入口和分发逻辑
- `feishu_handlers/message_handler.py`（~120 行）：消息处理
- `feishu_handlers/plan_handler.py`（~100 行）：计划处理
- `feishu_handlers/knowledge_handler.py`（~60 行）：知识库路由
- `feishu_handlers/menu_handler.py`（~50 行）：菜单状态
- `feishu_handlers/approval_handler.py`（~40 行）：审批处理

#### `backend/core/s01_agent_loop/agent_loop_run.py:60-63`
```python
# 当前（原地突变）
messages[:] = await compressor.compress(messages, tools)

# 建议：避免原地突变，返回新列表
compressed = await compressor.compress(list(messages), tools)
# 或使用不可变更新模式
```

#### `backend/common/types/session.py` + `backend/common/types/agent.py`
```python
# 当前：Schema 重复
# 建议：提取共享 BaseConfig
class BaseConfig(BaseModel):
    model: str
    provider: str = "anthropic"
    system_prompt: str = ""
    max_tokens: int = 16384
    temperature: float = 0.7

class SessionConfig(BaseConfig):
    pass

class AgentConfig(BaseConfig):
    workspace: str = ""
    session_id: str = ""
    thinking_enabled: bool = False
    tools: list[str] = Field(default_factory=list)
    max_iterations: int = 20
    max_consecutive_tool_failures: int = 5
    dead_end_reflection_iteration: int = 10
    timeout_seconds: float = 300.0
```

#### `backend/adapters/message_zones.py`
```python
# 建议：添加 ephemeral 过滤和消息去重
def request_zone_messages(request: LLMRequest, *, include_system: bool, include_ephemeral: bool = False) -> list[Message]:
    dynamic = [
        *request.skill_messages,
        *request.memory_messages,
        *request.runtime_messages,
        *([request.summary_message] if request.summary_message else []),
        *request.recent_messages,
    ]
    if not include_ephemeral:
        dynamic = [m for m in dynamic if not m.ephemeral]
    # 消息去重
    seen = set()
    deduped = []
    for m in dynamic:
        key = hash_message(m)
        if key not in seen:
            seen.add(key)
            deduped.append(m)
    return _with_system_first(deduped, request.system_prompt)
```

#### `backend/core/s06_context_compression/layered_compressor.py`
```python
# 建议：按模型动态调整阈值
class LayeredCompressorConfig(BaseModel):
    max_context_tokens: int = Field(default=180000)
    threshold_l2: float = Field(default=0.5)
    threshold_l3: float = Field(default=0.7)
    threshold_final: float = Field(default=0.9)
    
    @model_validator(mode="after")
    def adjust_for_model(self):
        # 根据实际模型上下文窗口调整
        if self.max_context_tokens > 128000:  # Claude 200K
            self.threshold_l2 = 0.6
            self.threshold_l3 = 0.75
        elif self.max_context_tokens <= 128000:  # GPT-4
            self.max_context_tokens = 120000  # 留余量
        return self
```

#### `backend/core/s02_tools/executor.py`
```python
# 建议：添加工具调用缓存
class ToolResultCache:
    def __init__(self, ttl_seconds: int = 300):
        self._cache: dict[str, tuple[ToolResult, float]] = {}
        self._ttl = ttl_seconds
    
    def _make_key(self, tool_name: str, args: dict) -> str:
        import hashlib
        return hashlib.sha256(f"{tool_name}:{json.dumps(args, sort_keys=True)}".encode()).hexdigest()
    
    def get(self, tool_name: str, args: dict) -> ToolResult | None:
        key = self._make_key(tool_name, args)
        if key in self._cache:
            result, ts = self._cache[key]
            if time.time() - ts < self._ttl:
                return result
            del self._cache[key]
        return None
    
    def set(self, tool_name: str, args: dict, result: ToolResult):
        key = self._make_key(tool_name, args)
        self._cache[key] = (result, time.time())
```

#### `backend/storage/session_store.py`
```python
# 建议：save_messages 改为增量追加
async def add_messages(self, session_id: str, messages: list[Message]) -> None:
    """增量追加消息，替代全量替换"""
    async with self._session() as db:
        for msg in messages:
            record = MessageRecord(
                session_id=session_id,
                role=msg.role,
                content=msg.content,
                tool_calls_json=msg.model_dump_json() if msg.tool_calls else None,
                # ...
            )
            db.add(record)
        await db.commit()
```

#### `backend/core/s01_agent_loop/plan_execute_runner.py`
```python
# 建议：添加动态重规划能力
async def replan(self, from_step_index: int, reason: str) -> ExecutionPlan:
    """从指定步骤开始重新规划剩余步骤"""
    completed_steps = self._plan.steps[:from_step_index]
    remaining_goal = f"{self._plan.goal}\n\n已完成步骤:\n" + "\n".join(
        f"{i+1}. {s.description}" for i, s in enumerate(completed_steps)
    )
    # 基于已完成结果重新生成计划
    new_plan = await self._generate_plan(remaining_goal, context=self._get_execution_context())
    # 合并已完成步骤和新计划
    self._plan.steps = completed_steps + new_plan.steps
    return self._plan
```

---

## 附录 A：关键文件索引

### Agent 编排层
- `backend/core/s01_agent_loop/agent_loop_run.py` — 主 Agent 循环
- `backend/core/s01_agent_loop/agent_loop.py` — AgentLoop 类定义
- `backend/core/s01_agent_loop/agent_loop_support.py` — LLM 请求构建、孤儿工具修复
- `backend/core/s01_agent_loop/agent_loop_guard.py` — 循环守卫
- `backend/core/s01_agent_loop/agent_loop_approval.py` — 人工审批
- `backend/core/s01_agent_loop/plan_execute_runner.py` — PlanExecuteRunner
- `backend/core/s01_agent_loop/plan_execute_runner_steps.py` — 计划步骤执行
- `backend/core/s01_agent_loop/plan_convergence.py` — 收敛监控
- `backend/core/s01_agent_loop/plan_recon.py` — Recon 阶段
- `backend/core/s01_agent_loop/plan_models.py` — 计划状态模型
- `backend/core/s01_agent_loop/plan_state_machine.py` — 计划状态机
- `backend/core/s01_agent_loop/plan_resume.py` — 计划恢复
- `backend/core/s01_agent_loop/plan_checkpoint_store.py` — 检查点存储
- `backend/core/s01_agent_loop/failure_recovery.py` — 失败恢复
- `backend/core/s01_agent_loop/tool_batching.py` — 工具批处理
- `backend/core/s01_agent_loop/tool_review.py` — 工具自动审查
- `backend/core/s01_agent_loop/message_history.py` — 消息历史

### 工具层
- `backend/core/s02_tools/executor.py` — 工具执行器
- `backend/core/s02_tools/registry.py` — 工具注册表
- `backend/core/s02_tools/security_gate.py` — 安全门控
- `backend/core/s02_tools/builtin/spawn_agent.py` — 子 Agent 派发
- `backend/core/s02_tools/builtin/spawn_agent_prepare.py` — 任务准备
- `backend/core/s02_tools/builtin/spawn_agent_wait.py` — 任务等待
- `backend/core/s02_tools/builtin/spawn_agent_support.py` — 结果格式化
- `backend/core/s02_tools/builtin/spawn_agent_templates.py` — 内联模板
- `backend/core/s02_tools/builtin/spawn_agent_governance.py` — 治理策略

### 子 Agent 层
- `backend/core/s04_sub_agents/isolated_runner.py` — 隔离运行器
- `backend/core/s04_sub_agents/permission_policy.py` — 权限策略
- `backend/core/s04_sub_agents/static_dag.py` — 静态 DAG 调度
- `backend/core/s04_sub_agents/dynamic_orchestrator.py` — 动态编排
- `backend/core/s04_sub_agents/scheduler_switch.py` — 调度器切换
- `backend/core/s04_sub_agents/result_contract.py` — 结果契约

### 技能层
- `backend/core/s05_skills/models.py` — AgentSpec 模型
- `backend/core/s05_skills/runtime.py` — AgentRuntime
- `backend/core/s05_skills/on_demand_loader.py` — 按需加载器
- `backend/core/s05_skills/runtime_support.py` — 运行时支持
- `backend/core/s05_skills/runtime_plan.py` — 计划执行模式
- `backend/core/s05_skills/loader.py` — 技能加载器
- `backend/core/s05_skills/registry.py` — 技能注册表

### 上下文压缩层
- `backend/core/s06_context_compression/layered_compressor.py` — 分层压缩器
- `backend/core/s06_context_compression/level1_artifact.py` — L1 Artifact
- `backend/core/s06_context_compression/level2_compact.py` — L2 紧凑化
- `backend/core/s06_context_compression/level3_summary.py` — L3 摘要
- `backend/core/s06_context_compression/compressor.py` — 传统压缩器
- `backend/core/s06_context_compression/token_counter.py` — Token 计数
- `backend/core/s06_context_compression/threshold_policy.py` — 阈值策略
- `backend/core/s06_context_compression/memory_index.py` — 记忆索引
- `backend/core/s06_context_compression/long_term_memory.py` — 长期记忆

### 任务系统层
- `backend/core/s07_task_system/executor.py` — 任务执行器
- `backend/core/s07_task_system/scheduler.py` — 任务调度器
- `backend/core/s07_task_system/cron_scheduler.py` — Cron 调度器
- `backend/core/s07_task_system/store.py` — 任务存储
- `backend/core/s07_task_system/runtime_state.py` — 运行时状态
- `backend/core/s07_task_system/card_notify.py` — 卡片通知

### 类型系统
- `backend/common/types/agent.py` — AgentConfig、AgentEvent
- `backend/common/types/llm.py` — LLMRequest、LLMResponse
- `backend/common/types/message.py` — Message、MessageKind
- `backend/common/types/session.py` — Session、SessionConfig
- `backend/common/types/tool.py` — ToolDefinition、ToolResult
- `backend/common/types/sub_agent.py` — SubAgent 类型
- `backend/common/types/mcp.py` — MCP 类型
- `backend/common/types/security.py` — SecurityPolicy、SignedToolCall

### API Schema
- `backend/schemas/session.py` — Session 请求/响应
- `backend/schemas/completion.py` — OpenAI 兼容请求/响应
- `backend/schemas/provider.py` — Provider 请求/响应
- `backend/schemas/feishu.py` — 飞书请求/响应

### 适配器层
- `backend/adapters/base.py` — LLMAdapter ABC
- `backend/adapters/factory.py` — AdapterFactory
- `backend/adapters/resilient_adapter.py` — ResilientLLMAdapter
- `backend/adapters/provider_manager.py` — ProviderManager
- `backend/adapters/provider_routing.py` — Provider 路由
- `backend/adapters/role_router.py` — 角色路由
- `backend/adapters/message_zones.py` — 消息 Zone 组装
- `backend/adapters/anthropic_adapter.py` — Anthropic 适配器
- `backend/adapters/openai_adapter.py` — OpenAI 兼容适配器
- `backend/adapters/ollama_adapter.py` — Ollama 适配器

### Route 层
- `backend/api/app.py` — FastAPI 应用入口
- `backend/api/routes/websocket.py` — WebSocket 端点
- `backend/api/routes/websocket_runtime.py` — WebSocket 运行时
- `backend/api/routes/websocket_pubsub.py` — WebSocket Pub/Sub
- `backend/api/routes/chat_completions.py` — OpenAI 兼容 API
- `backend/api/routes/feishu.py` — 飞书主路由
- `backend/api/routes/feishu_handler.py` — 飞书消息处理器
- `backend/api/routes/feishu_card_action.py` — 飞书卡片操作
- `backend/api/routes/feishu_events.py` — 飞书事件分发
- `backend/api/routes/sessions.py` — 会话 CRUD
- `backend/api/routes/knowledge.py` — 知识库
- `backend/api/routes/providers.py` — Provider 管理
- `backend/api/routes/mcp.py` — MCP 服务器管理

### 中间件
- `backend/api/middleware/auth.py` — 认证中间件
- `backend/api/middleware/request_trace.py` — 请求追踪中间件
- `backend/api/middleware/rate_limit.py` — 速率限制（空）
- `backend/api/middleware/error_handler.py` — 错误处理（空）

### 存储层
- `backend/storage/session_store.py` — 会话存储
- `backend/storage/sub_agent_task_store.py` — 子 Agent 任务存储

### 任务队列
- `backend/core/task_queue.py` — 任务队列
- `backend/core/task_queue_types.py` — 任务队列类型
- `backend/api/task_queue_consumer.py` — 任务队列消费者
- `backend/api/lifespan_support.py` — 生命周期支持

---

## 附录 B：框架对比（待补充）

> 注：AutoGen、LangGraph、CrewAI、Swarm 的详细对比因数据源问题未能完成。
>
> 建议后续补充以下维度的对比分析：
> - 架构模式（ReAct / Plan-and-Execute / 图编排）
> - 多 Agent 协调机制（消息传递 / 共享状态 / 函数调用）
> - 工具集成方式（内置 / MCP / 自定义）
> - 上下文管理策略（压缩 / 记忆 / 状态持久化）
> - 部署模式（本地 / 云端 / 混合）
> - 生态成熟度（社区规模 / 文档质量 / 第三方集成）
> - 与 Agent Studio 的映射关系和迁移路径
