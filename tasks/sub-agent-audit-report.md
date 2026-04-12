# 子 Agent (Sub-Agent) 系统安全审计报告

**审计日期**: 2026-04-07  
**审计范围**: `backend/core/s04_sub_agents/` 模块及关联代码  
**审计维度**: 派生隔离、权限策略、依赖推导、超时控制、结果聚合

---

## 1. 执行摘要

子 Agent 系统实现了完整的 Agent 派生、隔离和编排机制。系统采用多层防御策略，包括工具注册表隔离、权限策略控制、执行超时保护等。经审计发现 **3 个低风险问题** 和 **2 个改进建议**。

| 风险等级 | 数量 | 状态 |
|---------|------|------|
| 严重 (Critical) | 0 | - |
| 高 (High) | 0 | - |
| 中 (Medium) | 0 | - |
| 低 (Low) | 3 | 待修复 |
| 信息 (Info) | 2 | 建议采纳 |

---

## 2. 派生隔离机制审计

### 2.1 架构设计

子 Agent 隔离通过以下三层实现：

```
┌─────────────────────────────────────────────────────────────┐
│  Layer 1: 工具注册表隔离 (build_isolated_registry)          │
│  - 过滤递归工具 (dispatch_agent, orchestrate_agents)        │
│  - 白名单机制控制可用工具                                   │
├─────────────────────────────────────────────────────────────┤
│  Layer 2: 系统提示词隔离 (_build_sub_agent_system_prompt)   │
│  - 独立角色定义                                             │
│  - 隔离规则声明                                             │
├─────────────────────────────────────────────────────────────┤
│  Layer 3: 依赖数据隔离 (_build_task_with_dependencies)      │
│  - 仅注入显式声明的依赖                                     │
│  - 无法访问其他子 Agent 输出                                │
└─────────────────────────────────────────────────────────────┘
```

### 2.2 代码审查

**文件**: `backend/core/s04_sub_agents/spawner.py:70-83`

```python
def _build_child_registry(self, parent_registry: ToolRegistry, allowed_tools: list[str]) -> ToolRegistry:
    child_registry = ToolRegistry()
    allowed = set(allowed_tools)
    for definition in parent_registry.list_definitions():
        if definition.name in {"dispatch_agent", "orchestrate_agents"}:  # ✅ 阻止递归
            continue
        if allowed and definition.name not in allowed:  # ✅ 白名单过滤
            continue
        ...
```

**文件**: `backend/core/s04_sub_agents/isolated_runner.py:30-36`

```python
parts.extend([
    "规则：",
    "1. 你只能看到当前分配的任务和显式提供的依赖结果。",  # ✅ 信息隔离声明
    "2. 你不能与其他子 Agent 通信，也看不到主对话历史。",  # ✅ 通信隔离声明
    "3. 输出要结构化、可复用，便于后续阶段直接消费。",
    ...
])
```

### 2.3 审计发现

| 检查项 | 状态 | 说明 |
|--------|------|------|
| 递归调用防护 | ✅ 通过 | 递归工具被显式过滤 |
| 工具白名单 | ✅ 通过 | allowed_tools 限制可用工具 |
| 对话历史隔离 | ✅ 通过 | 子 Agent 无法访问父对话 |
| 数据注入控制 | ✅ 通过 | 仅注入 `depends_on` 声明的依赖 |
| 进程级隔离 | ⚠️ 信息 | 当前为协程级隔离，非进程级 |

**评估**: 隔离机制设计合理，能有效防止子 Agent 越权访问。但隔离级别为协程级，非操作系统进程级，理论上存在内存泄露风险（当前代码未发现）。

---

## 3. 权限策略审计

### 3.1 权限模型

```
┌────────────────────────────────────────────────────────┐
│  readonly (只读)                                       │
│  - 允许: Read, Bash(只读命令)                          │
│  - 阻止: Write, 危险 Bash 命令                         │
├────────────────────────────────────────────────────────┤
│  readwrite (读写)                                      │
│  - 允许: Read, Write, Bash                             │
│  - 无命令限制                                          │
└────────────────────────────────────────────────────────┘
```

### 3.2 代码审查

**文件**: `backend/core/s04_sub_agents/permission_policy.py:11-58`

```python
READONLY_BLOCKED_PATTERNS: list[str] = [
    r"\brm(\s|$)",           # 删除命令
    r"\bmv\s",               # 移动命令
    r"\bcp\s",               # 复制命令
    r"\bchmod\s",            # 权限修改
    r"\bsed\s+-i",           # 原地编辑
    r"(^|[^|])>(?![>&])",    # 输出重定向
    r">>",                   # 追加重定向
    r"\bgit\s+(commit|push|merge|rebase|checkout|reset|clean)\b",  # Git 写操作
    r"\bnpm\s+(install|uninstall|publish)\b",  # NPM 修改
    r"\bpip\s+(install|uninstall)\b",          # Pip 修改
    ...
]
```

**文件**: `backend/core/s04_sub_agents/permission_policy.py:113-131`

```python
async def readonly_bash(args: dict[str, object], _exec=original_executor) -> ToolResult:
    try:
        command = str(args.get("command", "")).strip()
        if is_readonly_blocked(command):  # ✅ 运行时检查
            raise PermissionPolicyError(f"readonly 模式下不允许执行修改命令: {command}")
        return await _exec(args)
    except PermissionPolicyError as exc:
        return ToolResult(output=f"权限拒绝: {exc.message}", is_error=True)
```

### 3.3 审计发现

#### 🔍 LOW-001: 命令注入绕过风险

**位置**: `permission_policy.py:74-82`

```python
def is_readonly_blocked(command: str) -> bool:
    normalized = command.strip().lower()
    if not normalized:
        return True
    if any(re.search(pattern, normalized) for pattern in READONLY_BLOCKED_PATTERNS):
        return True
    return _extract_command_prefix(normalized) in READONLY_BLOCKED_PREFIXES
```

**问题**: 使用正则表达式匹配命令存在潜在绕过风险：
- `echo "hello; rm file"` 可能绕过检测
- 复杂管道命令的检测可能不完整

**建议**: 
1. 考虑使用更严格的命令解析器
2. 添加命令复杂度限制
3. 记录所有被阻止的命令尝试

**风险等级**: 🔶 LOW

#### 🔍 LOW-002: PowerShell 别名绕过

**位置**: `permission_policy.py:37-58`

```python
READONLY_BLOCKED_PREFIXES = {
    "bash", "cmd", "powershell", "python", ...
}
```

**问题**: 仅阻止了标准可执行文件名，未考虑：
- `powershell_ise.exe`
- `pyw.exe` (Python Windows 无窗口版本)
- 脚本文件的直接执行

**风险等级**: 🔶 LOW

### 3.4 权限策略测试覆盖

| 测试用例 | 位置 | 状态 |
|----------|------|------|
| 危险命令阻止 | `test_permission_policy.py:19-33` | ✅ 通过 |
| 只读命令允许 | `test_permission_policy.py:35-37` | ✅ 通过 |
| Bash 包装器 | `test_permission_policy.py:40-78` | ✅ 通过 |
| 读写模式 | `test_permission_policy.py:81-98` | ✅ 通过 |
| 递归工具过滤 | `test_permission_policy.py:100-123` | ✅ 通过 |

---

## 4. 依赖推导审计

### 4.1 算法实现

**文件**: `backend/common/types/sub_agent.py:65-95`

```python
def resolve_stages(tasks: list[AgentTask]) -> list[ResolvedStage]:
    # 1. 角色唯一性检查
    task_order = [task.role for task in tasks]
    if len(task_order) != len(set(task_order)):
        raise ValueError("tasks 中的 role 不能重复")
    
    # 2. 依赖有效性检查
    for task in tasks:
        if task.role in task.depends_on:  # 自依赖检查
            raise ValueError(f"任务 {task.role} 不能依赖自己")
        for dependency in task.depends_on:
            if dependency not in known_roles:  # 未知依赖检查
                raise ValueError(f"任务 {task.role} 依赖了不存在的角色: {dependency}")
    
    # 3. 拓扑排序
    while pending:
        ready_roles = [...]  # 依赖已满足的任务
        if not ready_roles:  # 循环依赖检测
            raise ValueError("任务依赖存在循环，无法推导执行阶段")
        ...
```

### 4.2 审计发现

| 检查项 | 状态 | 说明 |
|--------|------|------|
| 角色唯一性 | ✅ 通过 | 重复角色名被拒绝 |
| 自依赖检测 | ✅ 通过 | 任务不能依赖自己 |
| 未知依赖检测 | ✅ 通过 | 依赖必须已定义 |
| 循环依赖检测 | ✅ 通过 | 拓扑排序检测循环 |
| 阶段推导 | ✅ 通过 | 并行任务正确分组 |

**评估**: 依赖推导算法正确实现了拓扑排序，能有效检测各种非法依赖配置。

### 4.3 依赖注入验证

**文件**: `backend/core/s04_sub_agents/isolated_runner.py:41-47`

```python
def _build_task_with_dependencies(run: IsolatedAgentRun) -> str:
    parts = [run.task.task]
    for role_name in run.task.depends_on:  # 仅注入显式依赖
        dependency_output = run.dependency_outputs.get(role_name)
        if dependency_output:
            parts.append(f"[来自 {role_name} 的结果]\n{dependency_output}")
    return "\n\n".join(parts)
```

**验证**: 依赖注入严格遵循 `depends_on` 声明，无法访问未声明的依赖输出。

---

## 5. 超时控制审计

### 5.1 实现机制

```
┌─────────────────────────────────────────────────────────────┐
│  层级 1: 生命周期管理 (SubAgentLifecycle)                   │
│  - 默认超时: 120 秒                                         │
│  - 活动任务计数                                             │
├─────────────────────────────────────────────────────────────┤
│  层级 2: 隔离运行超时 (isolated_runner.py)                  │
│  - asyncio.wait_for() 包装                                  │
│  - 超时错误转换                                             │
├─────────────────────────────────────────────────────────────┤
│  层级 3: AgentLoop 迭代限制                                 │
│  - max_iterations 限制 (默认 10)                            │
│  - max_consecutive_tool_failures 限制 (默认 3)              │
└─────────────────────────────────────────────────────────────┘
```

### 5.2 代码审查

**文件**: `backend/core/s04_sub_agents/lifecycle.py:10-36`

```python
class SubAgentLifecycle:
    def __init__(self, timeout: float = 120.0) -> None:
        self._timeout = timeout
        self._active_tasks: set[asyncio.Task[ToolResult]] = set()

    async def run_with_timeout(self, spawner: SubAgentSpawner, params: SpawnParams) -> ToolResult:
        task = asyncio.create_task(spawner.spawn_and_run(params))
        self._active_tasks.add(task)
        try:
            return await asyncio.wait_for(task, timeout=self._timeout)  # ✅ 超时控制
        except asyncio.TimeoutError:
            task.cancel()  # ✅ 任务取消
            return ToolResult(output=f"Sub-agent timed out after {self._timeout:.0f}s", is_error=True)
```

**文件**: `backend/core/s04_sub_agents/isolated_runner.py:76-87`

```python
result = await asyncio.wait_for(
    loop.run(_build_task_with_dependencies(run)),
    timeout=runtime.config.timeout_per_agent,  # ✅ 可配置超时
)
```

### 5.3 审计发现

#### 🔍 LOW-003: 任务取消后状态不一致

**位置**: `lifecycle.py:17-29`

```python
async def run_with_timeout(self, spawner: SubAgentSpawner, params: SpawnParams) -> ToolResult:
    task = asyncio.create_task(spawner.spawn_and_run(params))
    self._active_tasks.add(task)
    try:
        return await asyncio.wait_for(task, timeout=self._timeout)
    except asyncio.TimeoutError:
        task.cancel()  # ⚠️ 取消信号发送
        return ToolResult(...)
    finally:
        self._active_tasks.discard(task)  # ✅ 清理集合
```

**问题**: `task.cancel()` 发送取消信号但不一定立即停止任务。如果子 Agent 正在执行工具调用（如 Bash），取消可能延迟生效。

**建议**: 
1. 在 `finally` 块中等待任务实际完成
2. 添加取消超时保护

```python
finally:
    if not task.done():
        try:
            await asyncio.wait_for(task, timeout=5.0)  # 等待取消完成
        except asyncio.TimeoutError:
            pass  # 强制结束
    self._active_tasks.discard(task)
```

**风险等级**: 🔶 LOW

### 5.4 超时测试覆盖

| 测试用例 | 位置 | 状态 |
|----------|------|------|
| 超时错误标记 | `test_orchestrator.py:88-104` | ✅ 通过 |
| 超时消息格式 | `test_isolated_runner.py:95-103` | ✅ 通过 |
| 部分结果保留 | `test_orchestrator.py:101-104` | ✅ 通过 |

---

## 6. 结果聚合审计

### 6.1 实现机制

**文件**: `backend/core/s04_sub_agents/result_aggregator.py:10-42`

```python
class ResultAggregator:
    @staticmethod
    async def run_parallel(
        spawner: SubAgentSpawner,
        params_list: list[SpawnParams],
        max_concurrent: int = 3,  # ✅ 并发限制
    ) -> list[ToolResult]:
        semaphore = asyncio.Semaphore(max_concurrent)
        async def run_one(params: SpawnParams) -> ToolResult:
            async with semaphore:  # ✅ 信号量控制
                return await spawner.spawn_and_run(params)
        return list(await asyncio.gather(*(run_one(params) for params in params_list)))

    @staticmethod
    def merge_results(results: list[ToolResult]) -> ToolResult:
        outputs = [result.output.strip() for result in results if result.output.strip()]
        return ToolResult(
            output="\n\n---\n\n".join(outputs),  # ✅ 结果分隔
            is_error=any(result.is_error for result in results),  # ✅ 错误传播
        )
```

### 6.2 编排器结果处理

**文件**: `backend/core/s04_sub_agents/orchestrator.py:114-127`

```python
def _format_report(self, stages: list[ResolvedStage], results: list[SubAgentResult]) -> str:
    error_count = sum(1 for item in results if item.is_error)
    summary = f"多 Agent 协作完成，共 {len(stages)} 个阶段，{len(results)} 个任务。"
    if error_count:
        summary = f"{summary} 其中 {error_count} 个子任务失败。"  # ✅ 错误统计
    sections = [summary]
    for stage in stages:
        role_line = ", ".join(stage.task_roles)
        sections.append(f"\n--- 阶段 {stage.stage_id}: {role_line} ---")  # ✅ 阶段分隔
        for result in (item for item in results if item.stage_id == stage.stage_id):
            status = "失败" if result.is_error else "完成"  # ✅ 状态标记
            sections.append(f"\n[{result.role}] [{status}]")
            sections.append(result.output)
    return "\n".join(sections)
```

### 6.3 审计发现

| 检查项 | 状态 | 说明 |
|--------|------|------|
| 并发控制 | ✅ 通过 | Semaphore 限制最大并发数 |
| 结果分隔 | ✅ 通过 | `\n\n---\n\n` 分隔多个结果 |
| 错误传播 | ✅ 通过 | 任一任务失败标记整体错误 |
| 阶段报告 | ✅ 通过 | 按阶段组织输出 |
| 错误统计 | ✅ 通过 | 统计并显示失败任务数 |

**评估**: 结果聚合逻辑完整，能有效整合多 Agent 执行结果。

---

## 7. 安全测试覆盖

### 7.1 测试矩阵

| 测试文件 | 测试数 | 覆盖率 |
|----------|--------|--------|
| `test_sub_agents.py` | 6 | 工具注册、递归防护、基础功能 |
| `test_permission_policy.py` | 5 | 权限策略、命令过滤 |
| `test_orchestrator.py` | 5 | 编排执行、依赖注入、超时 |
| `test_isolated_runner.py` | 4 | 隔离运行、超时、依赖 |
| `test_sub_agent_models.py` | 5 | 模型验证、依赖推导 |
| `test_sub_agent_spawner_fallback.py` | - | 异常处理 |

### 7.2 缺失测试场景

| 场景 | 优先级 | 建议 |
|------|--------|------|
| 命令注入尝试 | 高 | 添加恶意命令绕过测试 |
| 深度递归依赖 | 中 | 测试多层依赖链 |
| 并发压力测试 | 中 | 大量并行任务测试 |
| 内存资源限制 | 低 | 测试大输出处理 |

---

## 8. 改进建议

### INFO-001: 添加审计日志

**建议**: 在关键安全节点添加审计日志：
- 子 Agent 创建/销毁
- 权限策略违规尝试
- 超时事件
- 依赖注入操作

```python
# 建议添加
logger.info("sub_agent_spawned", role=role_name, task_id=task_id)
logger.warning("permission_violation", role=role_name, command=blocked_command)
```

### INFO-002: 增强监控指标

**建议**: 添加 Prometheus 风格的指标：
- `sub_agent_active_count` - 活动子 Agent 数
- `sub_agent_execution_duration` - 执行时长分布
- `sub_agent_timeout_count` - 超时计数
- `sub_agent_permission_violations` - 权限违规计数

---

## 9. 总结

### 9.1 优势

1. **多层隔离**: 工具、提示词、数据三层隔离设计
2. **权限分级**: readonly/readwrite 两级权限模型
3. **依赖管控**: 严格的拓扑排序和依赖注入控制
4. **超时保护**: 多层级超时机制保护
5. **错误处理**: 完善的异常捕获和错误传播

### 9.2 待修复问题

| ID | 问题 | 文件 | 建议修复 |
|----|------|------|----------|
| LOW-001 | 命令注入绕过风险 | `permission_policy.py` | 增强命令解析 |
| LOW-002 | PowerShell 别名绕过 | `permission_policy.py` | 扩展阻止列表 |
| LOW-003 | 任务取消状态不一致 | `lifecycle.py` | 添加取消等待 |

### 9.3 审计结论

子 Agent 系统整体设计良好，安全机制较为完善。发现的 3 个低风险问题均不构成立即威胁，但建议在未来版本中修复。系统已具备生产环境部署的安全基础。

---

**审计人**: Claude Code Security Audit  
**报告版本**: 1.0  
**审核状态**: ✅ 完成
