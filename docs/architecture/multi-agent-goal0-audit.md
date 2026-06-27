# Multi-Agent Goal 0 Audit

本文是 `codex-execution-guide.md` 的 Goal 0 交付物。范围仅限现状调查和 build/复用决策，不包含产品代码改动。

## 结论

`backend/core/s04_sub_agents/orchestrator.py` 不是死代码。它仍通过 `orchestrate_agents` builtin 工具注册路径暴露，并且已经实现了按依赖拓扑分阶段、阶段内并行执行、依赖结果只传给声明依赖方。

按执行指南的【已定】规则，模式一应复用现有 `orchestrator.py` / `resolve_stages` 的 DAG 内核作为底座，但需要在后续 Goal 中包到新的共享契约里：

- 复用：`resolve_stages()` 的图校验与分阶段逻辑。
- 复用：`Orchestrator._run_stage()` 的阶段内并行执行形态。
- 复用/迁移：`Orchestrator._build_run()` 中按 `depends_on` 注入依赖结果的隔离思想。
- 必须补齐：统一 `TaskSpec`、`AgentResultV1`、运行时强制治理、失败传播、结构化输出、与当前 Redis `spawn_agent` worker 链路的共享执行层。

后续不应再新增第三套 DAG 系统；目标是把旧静态 DAG 能力吸收到共享层，让静态 DAG 与动态编排共用同一套任务契约、结果契约、治理和子 agent 运行时。

## 文件现状

| 文件 | 存在 | 当前职责 | Goal 0 判断 |
|---|---:|---|---|
| `backend/core/s02_tools/builtin/spawn_agent.py` | 是 | 当前推荐的并行子 agent 工具入口；解析 `tasks`，准备任务，提交到 Redis queue，等待所有结果并格式化文本报告。 | 当前主链路。后续治理与结果契约优先接这里。 |
| `backend/core/s02_tools/builtin/spawn_agent_support.py` | 是 | 定义 `SpawnAgentTask` / `SpawnAgentArgs` / `SpawnAgentDeps` / `PreparedTask`；完成 spec 校验、timeout 计算、payload 构造、结果格式化和事件通知。 | 可扩展为 Goal 1/2/3 的准备层，但当前缺少 `permission`、`depends_on`、结果契约等字段。 |
| `backend/api/task_queue_consumer.py` | 是 | sub-worker 消费 `TaskPayload`；构建 spec 或 inline 子 AgentLoop；执行 `loop.run()`；完成/失败写回 queue。也处理知识库入库任务。 | 当前 Redis worker 执行层。后续结果校验/返修更适合接在这里，避免重跑整个子 agent。 |
| `backend/core/task_queue.py` | 是 | Redis task queue：`submit` / `claim` / `complete` / `fail` / `wait_for_tasks` / `recover_stale_tasks`。 | 可继续复用。`submit()` 默认 `max_retries=1`，符合 worker 死亡回收方向。 |
| `backend/core/task_queue_support.py` | 是 | wait 超时处理、RUNNING lease 过期回收、终态写入保护。 | 已有 stale recovery：过期 RUNNING 任务在 `retry_count < max_retries` 时重新入队，否则失败。 |
| `backend/core/sub_agent_queue.py` | 是 | 创建 `sub_agent` namespace 队列，TTL 86400 秒，claim block 1 秒。 | 当前主队列工厂，可复用。 |
| `backend/sub_worker.py` | 是 | sub-worker 入口；启动多个 consumer，并每 30 秒执行 `queue.recover_stale_tasks()`。 | worker 回收闭环存在。 |
| `backend/core/s04_sub_agents/orchestrator.py` | 是 | 旧静态 DAG 编排器；调用 `resolve_stages()`，逐阶段执行，阶段内 `asyncio.gather` 并行，汇总文本报告。 | 仍可用，且满足“拓扑分阶段 + 阶段内并行”。复用为模式一内核。 |
| `backend/core/s04_sub_agents/isolated_runner.py` | 是 | 旧 isolated 子 agent 执行器；构建独立 AgentLoop、隔离 registry、拼接依赖输出、按 timeout 运行。 | 可复用隔离思想，但后续应与 Redis worker 的共享运行时收敛。 |
| `backend/core/s04_sub_agents/permission_policy.py` | 是 | 旧 isolated registry 权限过滤；readonly 默认只给 `Read`/`Bash`，并拦截写入型 Bash 命令。 | 可借鉴，但它只覆盖旧 `orchestrate_agents`/`dispatch_agent` 路径。 |
| `backend/core/s05_skills/runtime_support.py` | 是 | 当前 AgentRuntime 工具注册过滤；按 `allowed_tools` 裁剪工具，`is_sub_agent` 和 `max_depth` 阻断递归工具。 | 当前递归边界主要在这里和 builtin 注册条件中生效。 |
| `backend/core/s05_skills/models.py` | 是 | 定义 `AgentSpec`、`ToolConfig`、`SubAgentPolicy(allowed_specs/max_concurrent/max_depth)`。 | `max_depth` 已参与工具注册；`allowed_specs` / `max_concurrent` 目前未在 `spawn_agent` 派发前强制执行。 |
| `backend/common/types/sub_agent.py` | 是 | 旧 `AgentTask` / `SimplePlan` / `SubAgentResult` / `resolve_stages()`。 | `resolve_stages()` 已具备空任务、重复 role、缺失依赖、自依赖、环依赖校验。 |
| `backend/core/s02_tools/builtin/orchestrate_agents.py` | 是 | 将 `SimplePlan` 暴露为 `orchestrate_agents` 工具，并调用旧 `Orchestrator.execute()`。 | 证明旧 orchestrator 仍有可调用入口。 |
| `backend/core/s02_tools/builtin/__init__.py` | 是 | builtin 工具注册中心。`orchestrate_agents` 在 workspace + auto/full + adapter + 非 sub-agent 条件下注册；`spawn_agent` 在 task_queue/spec_registry + 非 sub-agent 条件下注册。 | 两条 multi-agent 入口并存。 |

## 调用关系

当前推荐链路：

```text
AgentLoop tool call: spawn_agent
  -> spawn_agent.prepare_tasks()
  -> TaskQueue.submit()
  -> sub_worker.consume_next_sub_agent_task()
  -> AgentRuntime.create_loop_from_id/create_loop_inline()
  -> child AgentLoop.run()
  -> TaskQueue.complete/fail()
  -> spawn_agent.wait_for_prepared_tasks()
```

旧静态 DAG 链路：

```text
AgentLoop tool call: orchestrate_agents
  -> SimplePlan.model_validate()
  -> Orchestrator.execute()
  -> resolve_stages()
  -> for each stage: asyncio.gather(run_isolated_agent(...))
  -> text report
```

`system_prompt.py` 当前只显式提示优先使用 `spawn_agent`，没有提示使用 `orchestrate_agents`。这说明 `spawn_agent` 是现在的主引导路径，但不代表 `orchestrate_agents` 已废弃；它仍由 builtin 注册中心暴露。

## 现有能力

- `resolve_stages()` 已实现拓扑分阶段，能拒绝未知依赖、重复 role、自依赖和环依赖。
- `Orchestrator._run_stage()` 使用 `asyncio.gather(..., return_exceptions=True)` 支持阶段内并行。
- `Orchestrator._build_run()` 只把 `task.depends_on` 中声明的依赖输出注入给子 agent，具备上下文隔离雏形。
- `isolated_runner.py` 会构建独立 AgentLoop，不继承主对话历史。
- `permission_policy.py` 在旧 isolated 路径中会移除递归工具，并对 readonly Bash 做写操作拦截。
- `TaskQueue` 和 `sub_worker` 已有 lease 过期扫描与重新入队机制，默认最多重试 1 次。

## 主要缺口

- `spawn_agent` 当前没有 `permission`、`depends_on`、`on_dep_failure`、`result_contract` 等字段。
- `SubAgentPolicy.allowed_specs` 和 `max_concurrent` 已定义，但当前 `spawn_agent.prepare_tasks()` 没有强制执行。
- 旧 `orchestrator.py` 输出是自然语言 `ToolResult`，不是 `AgentResultV1`。
- 旧 `orchestrator.py` 遇到上游失败后仍会把失败文本作为依赖输出传给下游，没有默认阻断下游。
- 旧 `orchestrator.py` 不走 Redis `TaskQueue` / sub-worker，不具备当前主链路的持久化、checkpoint 和跨 worker 执行能力。
- 当前 `spawn_agent` 是全并行批量派发，不支持静态 DAG 的阶段式 depends_on。
- readonly 权限策略在旧 isolated 路径和新 AgentRuntime 路径中不统一；新 inline 路径主要靠 `tools` 白名单裁剪，没有统一的 `permission` 语义。

## Build / 复用决策

决策：复用现有静态 DAG 内核，不删除 `orchestrator.py`，也不新建另一套并行 DAG 系统。

后续 Goal 的推荐落点：

1. Goal 1 先在 `spawn_agent` 派发准备层和 AgentRuntime 工具注册层强制执行治理。
2. Goal 2 在 sub-worker 完成前引入 `AgentResultV1` 校验、廉价返修和兜底，避免重跑整个子 agent。
3. Goal 3 把上下文隔离、工具限权和产物引用沉到共享运行时 helper。
4. Goal 4 将 `resolve_stages()` / 阶段并行逻辑适配到共享 `TaskSpec`，并接入当前 Redis worker 执行层；旧 `orchestrator.py` 的文本报告路径最终应成为兼容层或被共享调度器替代，避免长期双轨。

