# 多智能体协同评估报告：稳定性与可用性

> 评估日期：2026-06-12
> 范围：`backend/core/s04_sub_agents/`、`spawn_agent` 工具链、Redis 任务队列与 sub-worker、子 agent 治理与结果契约。
> 性质：现状分析与改进建议，不含代码改动。本文是对 `multi-agent-goal0-audit.md` 的延续与补充。

---

## 0. 一句话结论

主链路（`spawn_agent` → Redis 队列 → sub-worker → 子 AgentLoop）方向正确，已经具备持久化、租约心跳、超时回收、结构化结果契约、权限治理和最终审核——在“map-reduce 式并行扇出”场景下基本可用。

但当前存在三个层面的系统性风险：**(1) 三套多智能体编排系统并存，只有一套真正接入生产**；**(2) 父循环等待超时会强杀仍在运行的子任务，在队列拥塞时浪费算力并误报失败**；**(3) 任务复用没有新鲜度边界，可能在同一会话内无限期返回陈旧结果**。前两者直接影响协作稳定性，第三者影响最终结果可用性。

---

## 1. 现状架构盘点

项目里目前**同时存在三条多智能体路径**，能力、持久化、结果格式各不相同：

| 路径 | 入口工具 | 执行方式 | 结果格式 | 持久化 | 是否生产可达 |
|---|---|---|---|---|---|
| **主链路** | `spawn_agent` | Redis 队列 + sub-worker 进程 | `AgentResultV1` 结构化契约 | ✅ Postgres（`SubAgentTaskStore`） | ✅ **是**（系统提示词唯一引导） |
| 旧静态 DAG | `orchestrate_agents` | 进程内 `asyncio.gather` 分阶段 | 自然语言文本报告 | ❌ 无 | ⚠️ 工具仍注册，但提示词不引导 |
| 旧单发 | `dispatch_agent` | 进程内 `SubAgentSpawner` | `ToolResult` 文本 | ❌ 无 | ⚠️ 工具仍注册，但提示词不引导 |
| 新调度抽象 | （无） | `DynamicOrchestrator` / `StaticDagScheduler` | `AgentResultV1` | ❌ | ❌ **仅测试可达** |

### 关键发现：新调度抽象层是“死代码”

`s04_sub_agents/dynamic_orchestrator.py`、`static_dag.py`、`scheduler_switch.py` 设计得最干净——有统一的 `TaskSpec`/`AgentResultV1`、波次（wave）推进、断路器、`on_dep_failure` 依赖失败策略。但全仓检索表明：

- `DynamicPlanner` / `DynamicTaskRunner` 只有 `Protocol` 定义，**没有任何生产实现** `initial_wave` / `decide` / `verify`（`backend/core/s04_sub_agents/dynamic_orchestrator.py:54`）。
- `pick_scheduler` / `SchedulerSet` 除了 `s04` 内部与单测，**没有任何生产调用方**。

也就是说，`multi-agent-goal0-audit.md` 里明确写下的“后续不应再新增第三套 DAG 系统”这条原则，实际上已经被违反——`static_dag.py` + `dynamic_orchestrator.py` 正是没接进主链路的第三套。这是最大的架构债务来源：**契约（`TaskSpec` vs `SpawnAgentTask`）、依赖语义、权限治理在三套里各写一遍，行为容易漂移**。

---

## 2. 稳定性分析

### 🔴 P0-1：父循环等待超时会强杀仍在运行的子任务（队列拥塞下浪费算力 + 误报失败）

这是本次评估最重要的发现，是一个真实的竞态。

**链路：**
- 父循环调用 `wait_for_prepared_tasks`，全局等待上限
  `global_timeout = min(max(timeout_seconds) * 2, 600)`（`spawn_agent_wait.py:30`）。
- 到达 deadline 后 `wait_for_task_payloads` 调用 `_fail_stuck_tasks`，对所有非终态任务执行 `queue.fail(task_id, "等待超时，主 agent 放弃等待")`（`task_queue_support.py:38`、`:166`）。
- `SubAgentTaskStore.fail` 只校验 `status == RUNNING`、**不校验是否真的超时**，于是把一个**正在被 worker 执行**的任务直接置为 `FAILED`（`storage/sub_agent_task_store.py:77`）。
- worker 随后正常跑完，调用 `complete(task_id, ..., worker_id)`，发现 `status != RUNNING` → 返回 `False` → 日志 `sub_agent_task_complete_discarded` → 再 `_safe_fail`（`task_queue_consumer.py:88`）。**子 agent 的成果被丢弃。**

**触发条件：队列排队延迟 > 单任务超时。**
- 父等待时钟从 `submit` 起算（含排队时间 Q）；worker 自己的 `asyncio.wait_for(loop.run, timeout)` 从 `claim` 起算（不含 Q）。
- worker 并发默认只有 2、最多 6（`settings.py:35-36`）。当多个父循环或单父循环派发的任务数 > 可用 worker 数时，后面的任务在队列里排队 Q 秒。
- 若 `Q > timeout`，worker 在父循环放弃后才跑完 → 命中上述竞态。`timeout=120` 时，只要队列积压让某任务排队超过 ~120s，就会发生。

**后果：** 高负载下用户看到“等待超时，主 agent 放弃等待”的失败，**而实际工作本可成功**；算力被白白消耗；`success_count` 偏低导致整体 `is_error` 误判。

**修复方向：**
1. `_fail_stuck_tasks` 不应强杀 `RUNNING` 且租约仍在续期（heartbeat 活跃）的任务——这类任务应判定为“仍在执行、父循环 detach”，而非 `FAILED`。
2. 让晚到的 `complete` 对已被“等待超时”置失败的任务**幂等补写成功**（late completion），避免成果丢弃。
3. 父全局等待上限应考虑队列深度（如 `global_timeout` 计入预估排队时间），或对排队中（PENDING）与执行中（RUNNING）区别对待。

### 🟠 P1-2：主链路（durable path）不支持 `depends_on`，多阶段依赖被迫回退给父循环

`spawn_agent` 是“一次性全并行扇出 + 等待全部”，`SpawnAgentTask` 没有 `depends_on` / 阶段字段（`spawn_agent_support.py:19`）。真正的 DAG 能力只存在于：
- 进程内、无持久化的旧 `orchestrate_agents`（`resolve_stages` + 阶段并行）；
- 未接线的 `static_dag.py`。

系统提示词因此只能告诉模型“子任务之间有先后依赖……不要派子 agent”（`core/system_prompt.py:63`）——即把依赖型工作推回父循环串行做。**结果是：有依赖关系的多智能体工作流在可持久化的主链路上无法表达**，要么牺牲持久化走旧路径，要么不并行。

**修复方向：** 把 `resolve_stages` + `on_dep_failure` 的阶段调度能力吸收进 `spawn_agent` 主链路（正是 audit 文档 Goal 4 的落点），用统一的 `TaskSpec` 替代 `SpawnAgentTask`，让 `static_dag.py` 真正接入而不是空转。

### 🟠 P1-3：只读权限在新旧两套路径中实现不一致，旧路径用黑名单（易绕过）

- **新路径**（`spawn_agent`）：`filter_tools_for_permission` 直接按工具名移除写工具（含 `Bash`），`enforce_child_loop_permission` 再从子 loop registry 移除——**白名单式，较稳**（`spawn_agent_governance.py:110`、`task_queue_consumer_governance.py:17`）。
- **旧路径**（`orchestrate_agents` / `dispatch_agent`）：`permission_policy.py` 保留 `Bash`，靠正则黑名单 `READONLY_BLOCKED_PATTERNS` 拦截写命令（`permission_policy.py:667`）。

正则黑名单天然易漏：`python -c "open('x','w')"`、`env A=1 cmd`、子 shell 重定向、`base64 -d | sh`、`xargs`、不在前缀表里的解释器等都可能绕过。两条 readonly 语义不统一，**旧路径的只读保证弱于新路径**。由于旧工具仍在 `auto/full` 模式下注册（`builtin/__init__.py:85`），这是一个实打实的越权面。

**修复方向：** 旧路径退役或统一收敛到白名单式权限模型；至少在 readonly 下也对旧路径移除 `Bash` 而非正则过滤。

### 🟡 P2-4：派发容量检查存在 TOCTOU 竞态

`_enforce_dispatch_capacity` 先 `get_children` 读取在途子任务数，校验后再 `submit`（`spawn_agent.py:138`）。读取与提交非原子，两个并发 `spawn_agent`（或未来的多波次）可能同时通过检查再各自提交，**突破 `max_concurrent`**。当前单父循环单 turn 内串行，影响有限；但在多 worker / 并行工具调用场景会暴露。

**修复方向：** 用 DB 事务 / Redis Lua 原子化“计数 + 占位”，或在提交侧用唯一约束兜底。

### 🟡 P2-5：最终审核（final-reviewer）自动注入，带来固定额外成本且占用并发预算

只要 `parent_task_id` 存在、子任务 ≥ 2 且至少 1 个成功，就会自动再派一个 `final-reviewer` 子 agent（180s 超时），并计入 `max_concurrent`（`spawn_agent_final_review.py:51`）。这意味着 Feishu 路径上**几乎每次多 agent 任务都会多付一个子 agent 的延迟与成本**，且有可能把并发顶到 `max_concurrent` 上限。

**修复方向：** 让 final-review 成为 policy 级可配置开关；将其排除在 `max_concurrent` 预算外或单独计量。

### 🟡 P2-6：结果契约修复（LLM repair）引入尾延迟，且无修复率指标

子 agent 输出非合法 JSON 时，`coerce_agent_result` 会调用 LLM 最多 2 次、每次 20s 超时来“返修”格式（`result_contract.py:193`）。最坏情况每个坏结果 +40s。若某模型不遵守契约，**每个子任务都触发返修**，整体延迟与成本放大。目前没有把“返修率 / 兜底率”做成可观测指标。

**修复方向：** 暴露 repair-rate / unparsed-rate 指标；对已知不守契约的模型走更强的输出约束（如工具调用强制结构化）而非事后返修。

### 🟢 设计性约束（非缺陷，但需明确记录）

- **递归深度仅 1 层**：`max_depth=1` 且 `is_sub_agent=True` 会剥离 `spawn_agent`/`dispatch_agent`/`orchestrate_agents`（`runtime_support.py:15`）。子 agent 不能再派子 agent——这是有意的稳定性边界，但也限制了深层分解。
- **子 agent 之间零通信**：依赖只能经父循环以 `dependency_outputs` 注入（`isolated_runner.py:577`）。适合 map-reduce，不支持协商式协作。
- **部分失败的整体标记偏宽**：`format_result` 仅在**全部失败**时置 `is_error=True`（`spawn_agent_support.py:59`）。部分失败会以“成功”姿态返回，把失败文本混在结果里交给父模型自行判断，可能导致父循环在残缺结果上直接汇总。

---

## 3. 可用性（最终结果可用性 / 系统可用性）分析

### 🔴 P0-7：任务复用没有新鲜度边界，可能无限期返回陈旧结果

`spawn_agent` 会复用同一 `parent_task_id`（即 session_id）下、输入哈希一致的历史 `SUCCEEDED` 子任务（`spawn_agent.py:147`、`_reuse_key` 见 `:175`）。问题：

- 复用判定走 `get_children(parent_task_id)` 查 Postgres，**没有任何时间过滤**（`sub_agent_task_store.py:131`）。Redis 缓存 TTL 是 24h，但持久化行只要不被清理就一直在——**复用实际上没有上限，不是“24h 内”而是“行还在就一直复用”**。
- 对实时性任务（实时行情、代理状态、新闻）尤其危险：同一会话里再问一次同样的问题，会**静默返回旧答案**，用户侧只有事件里的 `reused` 计数能看出端倪。

**修复方向：** 给复用加新鲜度谓词（TTL / `no_cache` 标志 / 按 spec 类别禁用复用），对时间敏感型 spec 默认不复用，并把“复用了 N 条历史结果”显式呈现给用户。同时为 `SubAgentTaskRecord` 增加 GC（目前只有 artifact GC，任务行无清理）。

### 影响可用性的其他点（已在第 2 节展开，此处汇总）

- **P0-1 的等待超时强杀**：高负载下直接表现为“本可成功却报失败”，是最大的最终可用性杀手。
- **P1-2 缺依赖编排**：复杂交付（先调研→再分头深挖→再汇总）在主链路无法一次完成，需父循环多轮，最终交付链路更脆。
- **P2-5 final-review**：提升了 Feishu 文件交付的可信度（完整性/排版兜底），这一点对“最终可用性”是正向的；但成本与并发占用要权衡。

### 系统级可用性（来自 `route-layer-agent-architecture-review.md`，与多智能体强相关）

以下几条直接影响**多 worker / 重启恢复 / 水平扩展**下的协同稳定：

- `backend/core/task_queue_consumer.py` 从 `backend.api.task_queue_consumer` 反向 re-export，`sub_worker.py` 也直接 import API 包——**core → api 依赖倒置**。task consumer 不应放在 API 包里。
- 运行态用进程内 dict 保存（`websocket.py` 的 `_loops`/`_plan_runners`/`_tasks`、`feishu_handler.py` 的 `_sessions` 等）——**对多 worker、重启恢复、水平扩展不友好**。子任务本身已持久化，但父循环/plan runner 的运行态没有，重启即丢。
- 多 agent policy 定义在 `api/routes/feishu_multi_agent_policy.py`——平台级策略放在了路由层，应下沉到 `core`。

---

## 4. 做得好的地方（应保留）

- **租约 + 心跳 + 超时回收闭环完整**：`claim` 设 `lease_expires_at`，heartbeat 每 15s 续 60s（`task_queue_consumer.py:26`），sub-worker 每 30s `recover_stale_tasks` 重新入队，`retry_count < max_retries` 时重试、否则置失败（`task_queue_support.py:50`）。worker 崩溃可恢复。
- **claim 用 `SELECT ... FOR UPDATE SKIP LOCKED`**：多 worker 抢占无重复消费（`sub_agent_task_store.py:40`）。
- **complete/fail 带 worker_id 归属校验**：防止过期 worker 写回（`sub_agent_task_store.py:67`、`:83`）。
- **checkpoint 恢复**：重试时从 `MessageRecord` 恢复子 agent 历史并续跑，而非整体重来（`task_queue_consumer.py:184`）。
- **大输出归档**：`sink_large_agent_output` 超阈值落盘并回传引用，避免上下文爆炸（`shared_runtime.py:502`）。
- **worker 池自动伸缩**：按 `unfinished` 在 `[default, max]` 间扩缩（`sub_worker_scaler.py`）。
- **结构化结果契约 + 兜底**：`AgentResultV1` + `unparsed` 降级，不会因一个坏输出整链崩。
- **依赖拓扑校验严谨**：`resolve_stages` 能拒绝重复 role、自依赖、未知依赖、环依赖（`common/types/sub_agent.py:67`）。

---

## 5. 改进建议（按优先级）

### P0（先做，直接影响稳定性与可用性）

1. **修复父等待 vs worker 执行的竞态**（对应 P0-1）
   - `_fail_stuck_tasks` 跳过租约仍活跃的 `RUNNING` 任务，标记为“detached/仍在执行”而非 `FAILED`。
   - 让晚到的 `complete` 对“等待超时”任务幂等补写成功，杜绝成果丢弃。
   - `global_timeout` 计入队列深度，避免排队时间挤占执行时间。

2. **给任务复用加新鲜度边界**（对应 P0-7）
   - 复用查询加 TTL 过滤；新增 `no_cache` / 按 spec 类别禁用；时间敏感型默认不复用。
   - 为 `SubAgentTaskRecord` 增加 GC。
   - 把“复用 N 条历史结果”显式呈现。

3. **收敛多智能体系统为一套**（对应 §1）
   - 以 `spawn_agent` + 统一 `TaskSpec`/`AgentResultV1` 为唯一主路径。
   - 要么把 `static_dag.py`/`dynamic_orchestrator.py` 真正接入主链路，要么删除，终结“三套 DAG”。
   - 统一 readonly 权限到白名单模型，退役正则黑名单路径（对应 P1-3）。

### P1

4. **主链路支持 `depends_on` / 阶段调度**（对应 P1-2）：复用 `resolve_stages` + `on_dep_failure`，让依赖型工作流在可持久化路径上一次跑完。
5. **改进部分失败语义**（对应设计约束）：向父循环回传结构化的逐任务状态与重试入口；关键任务失败时即应标记 `is_error`，而非仅“全失败”才标记。
6. **final-review 可配置**（对应 P2-5）：policy 级开关，且不挤占 `max_concurrent` 预算。
7. **落实 route 层 P0 建议**：把 `task_queue_consumer*` 移出 `api` 包，消除 core→api 反向依赖；多 agent policy 下沉到 `core`。

### P2

8. **可观测性补全**：把 `SubAgentTrace`（spawned/completed/failed + token）接入真实主链路（目前只服务于未接线的 `DynamicOrchestrator`）；暴露 repair-rate、reuse-rate、queue-depth、parent-wait-timeout 计数指标。
9. **派发容量原子化**（对应 P2-4）：DB 事务 / Redis Lua 消除 TOCTOU。
10. **异步 / detached 派发模式**：返回句柄、轮询或流式获取，避免长多 agent 任务长时间占住父 turn。
11. **运行态去进程内化**：引入 `RunRegistry`，区分 durable state 与 process-local handle，支撑重启恢复与水平扩展。

---

## 6. 附录：关键文件索引

| 关注点 | 文件 |
|---|---|
| 主链路工具 | `backend/core/s02_tools/builtin/spawn_agent.py` |
| 任务准备 / 复用 | `spawn_agent_prepare.py`、`spawn_agent.py:_split_reused_tasks` |
| 父循环等待 | `spawn_agent_wait.py`、`core/task_queue_support.py` |
| worker 消费 | `backend/api/task_queue_consumer.py` |
| 治理（权限/预算/契约） | `task_queue_consumer_governance.py`、`spawn_agent_governance.py` |
| 结果契约 | `s04_sub_agents/result_contract.py` |
| 持久化 | `backend/storage/sub_agent_task_store.py` |
| 任务队列 | `backend/core/task_queue.py`、`task_queue_support.py` |
| 未接线的新调度抽象 | `s04_sub_agents/dynamic_orchestrator.py`、`static_dag.py`、`scheduler_switch.py` |
| 旧路径 | `s04_sub_agents/orchestrator.py`、`isolated_runner.py`、`permission_policy.py` |
| 子 agent 策略 | `core/s05_skills/models.py`、`api/routes/feishu_multi_agent_policy.py` |
| 前序评估 | `multi-agent-goal0-audit.md`、`route-layer-agent-architecture-review.md` |
