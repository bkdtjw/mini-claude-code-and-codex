# MCP 功能审计报告

审计方式：只读静态审计，逐一阅读任务要求中的 MCP 相关文件，并补充核对 `ToolRegistry`、`ToolExecutor`、`SecurityGate`、`AgentLoop`、测试与配置文件。未修改代码，未启动真实 MCP server。

## 1. 调用链路

### 链路 A：添加并连接一个 MCP server

1. HTTP `POST /api/mcp/servers` 进入 `backend/api/routes/mcp.py:add_server`。
2. 路由调用全局 `mcp_server_manager.add_server(body)`。
3. `backend/core/s02_tools/mcp/server_manager.py:MCPServerManager.add_server`
   - `_load_from_file()` 读取 `backend/config/mcp_servers.json`
   - 检查 `config.id` 是否重复
   - 先写入 `_servers`，再 `_save_to_file()`
   - 若 `enabled=True`，继续 `connect_server(server_id)`
4. `MCPServerManager.connect_server`
   - `_require_server(server_id)` 取配置
   - 创建或复用 `MCPClient`
   - `client.connect()`
   - `client.list_tools()`
   - 将工具列表写入 `_tool_cache`
5. `backend/core/s02_tools/mcp/client.py:MCPClient.connect`
   - 创建 `AsyncExitStack`
   - `_open_transport()` 打开 `stdio` 或 `sse` 传输
   - 创建 `ClientSession` 并 `initialize()`
6. API 返回 `_get_status(server_id)` 的 `MCPServerStatus`。
7. 关键缺口：这条 HTTP 链路不会把工具注册到任何现存 `ToolRegistry`。工具真正进入 agent 可见范围，发生在后续 chat/websocket/CLI 新建 session 时：
   - `backend/api/routes/chat_completions.py:98`
   - `backend/api/routes/websocket.py:115`
   - `backend/cli_support/session.py:96`
   它们都会新建 `ToolRegistry`，然后调用 `MCPToolBridge.sync_all()`。

### 链路 B：Agent 调用一个 MCP 工具

1. chat/websocket/CLI 在创建 loop 时调用 `MCPToolBridge.sync_all()`。
2. `backend/core/s02_tools/mcp/tool_bridge.py:MCPToolBridge.sync_all`
   - `list_servers()`
   - 对每个 `enabled` server 执行 `sync_server_tools(server_id)`
3. `sync_server_tools`
   - `remove_server_tools(server_id)` 清旧工具
   - `server_manager.refresh_tools(server_id)` 拉最新工具
   - `_build_definition()` 生成 `mcp__{server_id}__{tool_name}`
   - `registry.register(definition, executor)` 注册执行器
4. `backend/core/s01_agent_loop/agent_loop.py:AgentLoop.run`
   - LLM 返回 `tool_calls`
   - `SecurityGate.authorize(response.tool_calls)`
   - `ToolExecutor.execute_signed_batch(...)`
5. `backend/core/s02_tools/executor.py:ToolExecutor.execute_signed`
   - `gate.verify(...)`
   - `execute(tool_call)`
6. `ToolExecutor.execute`
   - 从 `ToolRegistry` 取出 MCP executor
   - 调用 `MCPToolBridge._build_executor.execute`
7. MCP executor
   - `server_manager.get_client(server_id)`
   - 如未连接则 `connect_server(server_id)`
   - `client.call_tool(tool_name, args)`
8. `MCPClient.call_tool`
   - `_ensure_session()`
   - `session.call_tool(...)`
   - 结果转成 `MCPToolResult`
9. bridge 将 `MCPToolResult` 转为项目内 `ToolResult`，再回到 `AgentLoop`，追加为 `Message(role="tool")`。

### 链路 C：断开并移除一个 MCP server

1. HTTP `DELETE /api/mcp/servers/{server_id}` 进入 `backend/api/routes/mcp.py:remove_server`。
2. 路由调用 `mcp_server_manager.remove_server(server_id)`。
3. `MCPServerManager.remove_server`
   - `_load_from_file()`
   - `disconnect_server(server_id)`
   - 从 `_servers` 删除
   - `_save_to_file()`
4. `MCPServerManager.disconnect_server`
   - 从 `_clients` pop client
   - `client.disconnect()`
   - 删除 `_tool_cache[server_id]`
   - 返回 status
5. `MCPClient.disconnect`
   - `AsyncExitStack.aclose()`
   - 清空 `_session` / `_stack`
6. 关键缺口：这条链路不会调用 `MCPToolBridge.remove_server_tools()`；现存 websocket/CLI registry 里的 MCP 工具不会被移除。

## 2. 发现的问题

### 🔴 严重

**F1. 未鉴权的 MCP 管理 API 直接暴露本地命令执行与 SSRF 能力**  
位置：`backend/api/app.py:31-46`，`backend/api/routes/mcp.py:37-89`，`backend/common/types/mcp.py:10-18`，`backend/core/s02_tools/mcp/client.py:104-116`，`backend/config/settings.py:15`。  
描述：应用没有接入 auth middleware；`/api/mcp/servers` 直接接受任意 `command`、`args`、`env`、`url`，随后可持久化并启动本地 stdio 命令，或发起 SSE 连接。  
触发条件：服务对外可访问时，请求方调用 MCP 管理接口。  
影响范围：远程攻击面直接包含本机进程启动、环境变量注入、内网 URL 访问。严格说这里不是 shell 字符串拼接注入，而是更严重的“任意命令配置并执行”。

**F2. `requires_approval=True` 没有形成真实拦截，MCP 工具默认可被自动调用**  
位置：`backend/core/s02_tools/mcp/tool_bridge.py:74`，`backend/core/s02_tools/security_gate.py:85-92`，`backend/core/s01_agent_loop/agent_loop.py:43-45`，`backend/api/routes/chat_completions.py:99`，`backend/api/routes/websocket.py:116`，`backend/cli_support/session.py:97`。  
描述：bridge 确实把 MCP 工具标记为 `requires_approval=True`、`sandboxed=False`，但 `SecurityGate` 从未读取 `ToolDefinition.permission.requires_approval`，只在 `allowed_tools` 非空时才做白名单限制；而三条主入口创建 `AgentLoop` 时都没有传非空 MCP 白名单。  
触发条件：任何正常 chat/websocket/CLI 会话中，LLM 产出 MCP 工具调用。  
影响范围：MCP 工具在默认路径下等同于“自动批准且不沙箱”，与权限元数据表达的含义相反。

**F3. `add_server` 先落盘再连接，失败后留下脏配置和脏 client 状态**  
位置：`backend/core/s02_tools/mcp/server_manager.py:29-42`，`backend/core/s02_tools/mcp/server_manager.py:95-106`。  
描述：`add_server` 在 `connect_server` 前就把 server 写入 `_servers` 并保存文件；`connect_server` 又会在连接成功前把 client 放进 `_clients`。如果连接失败，调用方收到失败，但配置已经落盘，后续同 id 再添加会报已存在。  
触发条件：新增 server 时命令错误、SDK 缺失、网络失败、初始化失败。  
影响范围：状态不一致，失败请求会制造“看起来没加成功、实际已经加进配置”的半成功状态。

**F4. remove/disconnect 不会驱动活跃 registry 反注册，旧工具会继续暴露给 Agent**  
位置：`backend/api/routes/mcp.py:54-89`，`backend/core/s02_tools/mcp/server_manager.py:44-52`，`backend/core/s02_tools/mcp/tool_bridge.py:53-60`，`backend/api/routes/websocket.py:154-166`，`backend/cli_support/session.py:59-148`。  
描述：HTTP 删除/断开只影响 manager、client 和配置文件，不会通知已创建的 websocket loop / CLI session 重建 registry，也不会调用 `remove_server_tools()`。  
触发条件：会话已经创建后，再通过 HTTP 增删断开 MCP server。  
影响范围：新增工具不会进入旧会话；已删除工具仍留在旧会话的 schema 里，调用时才报错；`disconnect` 后旧 executor 还会自动重连。

**F5. manager/client 缺少并发保护，存在重复连接、状态覆盖和资源泄漏风险**  
位置：`backend/core/s02_tools/mcp/server_manager.py:23-27`，`backend/core/s02_tools/mcp/server_manager.py:95-101`，`backend/core/s02_tools/mcp/client.py:24-42`。  
描述：`_servers`、`_clients`、`_tool_cache`、配置文件读写都没有锁；`MCPClient.connect()` 也没有连接锁。并发 `connect_server()` 时，多个协程可能同时对同一个 client 建 transport/session，最后只保留后写入的 `_session/_stack`。  
触发条件：多个请求/会话同时同步或调用同一 MCP server。  
影响范围：重复子进程、重复 SSE 会话、悬空 `AsyncExitStack`、registry 短暂缺工具或重复注册异常。

### 🟠 中等

**F6. 没有连接/列工具/调工具超时，也没有健康检查与自动重连**  
位置：`backend/core/s02_tools/mcp/client.py:24-42`，`backend/core/s02_tools/mcp/client.py:54-83`，`backend/core/s02_tools/mcp/client.py:85-117`。  
描述：`connect`、`list_tools`、`call_tool` 都直接 await 底层 SDK；`is_connected` 只看 `_session` 和 `_stack` 是否非空，不判断 stdio 子进程或 SSE 连接是否仍存活。  
触发条件：server 卡住、无响应、进程崩溃、SSE 断流。  
影响范围：请求或 AgentLoop 可能无限等待；坏连接会被反复复用，直到手工清理。

**F7. 当前同步路径重复拉工具，且每次新会话都会对所有 enabled server 做全量同步**  
位置：`backend/core/s02_tools/mcp/server_manager.py:72-80`，`backend/core/s02_tools/mcp/server_manager.py:95-101`，`backend/core/s02_tools/mcp/tool_bridge.py:41-47`，`backend/api/routes/chat_completions.py:98`，`backend/api/routes/websocket.py:115`，`backend/cli_support/session.py:96`。  
描述：`refresh_tools()` 先 `connect_server()`，而 `connect_server()` 已经做了一次 `list_tools()`；返回后 `refresh_tools()` 又做第二次 `list_tools()`。chat 每个请求、websocket 每次重建 loop、CLI 每次重建 session 都会重复走这条链路。  
触发条件：存在 enabled MCP server。  
影响范围：工具列表请求翻倍，远端 server 越多、工具越多，启动延迟和网络/进程开销越大。

**F8. `sync_server_tools()` 是“先删后建”的非事务流程，失败时 registry 会进入半更新状态**  
位置：`backend/core/s02_tools/mcp/tool_bridge.py:26-39`。  
描述：它先删旧工具，再 refresh 再 register。任何一步失败，旧工具已消失，新工具可能只注册一部分。  
触发条件：server 临时异常、schema 异常、重复注册、调用 `refresh_tools()` 出错。  
影响范围：活跃会话的工具 schema 不稳定，Agent 可能在同一个 session 内看到工具集合抖动。

**F9. 会话与请求清理不完整，存在任务/子进程残留风险**  
位置：`backend/cli.py:11-29`，`backend/cli_support/session.py:59-122`，`backend/api/routes/chat_completions.py:105-136`，`backend/api/app.py:24-28`。  
描述：CLI 主流程没有 `finally: await session.mcp_manager.disconnect_all()`；streaming chat 在客户端断开时没有显式 `loop.abort()+task.cancel()`；FastAPI lifespan 在 shutdown 清理失败时会抛新异常，可能覆盖原始错误。  
触发条件：CLI 退出、HTTP stream 中断、应用 shutdown 时 MCP disconnect 抛错。  
影响范围：stdio server 子进程、后台 AgentLoop 任务和清理错误都可能残留或被掩盖。

**F10. 配置模型缺少 transport 级校验，非法配置会被接受并延后到运行时爆炸**  
位置：`backend/common/types/mcp.py:10-18`，`backend/api/routes/mcp.py:37-41`。  
描述：`stdio` 不强制要求 `command`，`sse` 不强制要求 `url`，也没有对 `id`、`args`、`env`、`url` 做 allowlist/格式校验。  
触发条件：调用方提交不完整或恶意配置。  
影响范围：坏配置可写入文件并污染后续同步流程。

### 🟡 轻微

**F11. MCP 非文本/结构化结果支持不完整**  
位置：`backend/common/types/mcp.py:28-30`，`backend/core/s02_tools/mcp/client.py:123-141`。  
描述：`MCPToolResult.content` 只有字符串；`_format_tool_result()` 在已有 text 时会丢 `structuredContent`，也没有对图片、音频、blob/resource 做保真映射。  
触发条件：server 返回 text + structured data，或多模态/资源型结果。  
影响范围：协议能力被压扁成字符串，客户端无法利用更丰富的 MCP 返回。

**F12. 测试覆盖只覆盖最浅 happy path，几乎没有 MCP 失败路径、权限路径和集成路径测试**  
位置：`backend/tests/unit/test_mcp_integration.py:70-99`，`backend/tests/unit/test_security_gate.py:95-170`，`backend/tests/unit/test_cli_support.py:78-179`。  
描述：现有测试只覆盖 manager 持久化、bridge 注册 fake 工具，以及通用 SecurityGate 白名单逻辑；CLI 也只注入空 MCP manager。  
触发条件：任何真实 MCP 失败场景。  
影响范围：超时、SDK 缺失、server 崩溃、并发竞态、HTTP API、stale registry、权限绕过等关键路径都没有回归保护。

## 3. 缺失功能

1. **自动重连与健康检查**：当前坏连接只能靠失败后人工触发重建；业务影响是 MCP server 一次抖动就可能把整条工具链拖入持续失败。
2. **连接与工具调用超时**：没有超时意味着一个卡死的 server 就能卡住整个 AgentLoop。
3. **活跃会话中的工具热更新**：现在只有“新建 session 时同步”，没有配置版本、通知或 `tools/list_changed` 对应处理；websocket/CLI 最受影响。
4. **server 日志与可观测性**：没有 stdout/stderr 捕获、没有 per-server 最近错误、没有连接健康指标，排障成本高。
5. **Resources / Prompts / richer tool content 支持**：当前只接 tools，且结果被压成文本，无法承接 MCP 更完整的上下文能力。
6. **Streamable HTTP 传输**：当前只支持 `stdio` 与旧式 `sse`，与当前 MCP 规范的主流 HTTP 传输能力存在兼容缺口。
7. **secret/credential 托管**：`env` 仍以明文 JSON 落盘，没有外部 secret 引用或统一 redaction 机制。

参考：  
- MCP Overview: https://modelcontextprotocol.io/specification/2025-06-18/basic/index  
- MCP Resources: https://modelcontextprotocol.io/specification/draft/server/resources  
- MCP Prompts: https://modelcontextprotocol.io/specification/draft/server/prompts  
- MCP Transports: https://modelcontextprotocol.io/specification/2025-03-26/basic/transports

## 4. 安全性发现

1. **`requires_approval=True` 当前不构成安全边界**：MCP 工具被标成需审批，但默认运行路径并不会因为这个标记而阻断执行；`dangerous_tools` 字段也没有在 `SecurityGate` 中发挥作用。
2. **`allowed_tools` 只有在显式传入非空白名单时才有效**：当前 chat/websocket/CLI 正常入口没有给 MCP 设置专门白名单，因此默认是“注册即允许”。
3. **`env` 风险真实存在**：`stdio` 路径会把 `os.environ` 与配置中的 `env` 合并传给 MCP 子进程，既扩大了 secrets 暴露面，也允许配置覆盖子进程关键环境变量。
4. **`command/args` 不是传统 shell 注入，但风险更大**：这里没有 `shell=True` 之类的字符串拼接执行，因此“元字符注入”不是主要问题；真正的问题是未鉴权 API 允许持久化并启动任意本地程序。
5. **`url` 带来 SSRF/内网访问面**：`sse_client(url=...)` 没有域名、网段或协议限制。
6. **本地配置文件存在明文敏感信息**：`backend/config/mcp_servers.json:26-28` 存在 `GITHUB_PERSONAL_ACCESS_TOKEN=github_pat_...<redacted>`；虽已被 `.gitignore:21` 忽略且未被 git 跟踪，但它仍是明文落盘 secret，建议立即轮换。

## 5. 改进建议

### P0（必须修）

1. **封住远程攻击面**  
问题引用：F1、F2。  
建议方案：给 MCP 管理 API 加认证；默认只监听 `127.0.0.1`；限制 `command` / `url` 来源；把“注册 stdio server”能力收窄为受信任模板。  
预估改动范围：`backend/api/app.py`、`backend/api/routes/mcp.py`、`backend/common/types/mcp.py`、部署配置。

2. **把 MCP 权限模型做成真正的执行闸门**  
问题引用：F2。  
建议方案：`SecurityGate` 读取 `ToolDefinition.permission`；MCP 工具默认进入显式审批或专用白名单；`permission_mode` 对 MCP 工具同样生效。  
预估改动范围：`backend/core/s02_tools/security_gate.py`、`backend/core/s01_agent_loop/agent_loop.py`、`backend/core/s02_tools/mcp/tool_bridge.py`、入口层会话创建代码。

3. **把 add/connect/remove 改成事务化状态机，并补锁**  
问题引用：F3、F4、F5、F8。  
建议方案：为 manager/client 引入 `asyncio.Lock`；`add_server` 先验证与连接，成功后再落盘；remove/disconnect 时联动 registry invalidation；失败时明确回滚。  
预估改动范围：`backend/core/s02_tools/mcp/server_manager.py`、`backend/core/s02_tools/mcp/client.py`、`backend/core/s02_tools/mcp/tool_bridge.py`。

### P1（应该修）

4. **补超时、健康检查、自动重连和断链恢复**  
问题引用：F6。  
建议方案：为 `connect/list_tools/call_tool` 增加超时与 retry；坏连接失败后清空 session 并按策略重连；为 SSE/stdio 增加健康状态。  
预估改动范围：`backend/core/s02_tools/mcp/client.py`、`backend/core/s02_tools/mcp/server_manager.py`。

5. **让活跃 websocket/CLI 会话能感知 MCP 配置变化**  
问题引用：F4。  
建议方案：引入 MCP 配置版本号或事件总线；HTTP 增删断开后标记现存 loop 的 registry 过期，并在下一轮请求前重建。  
预估改动范围：`backend/api/routes/mcp.py`、`backend/api/routes/websocket.py`、`backend/cli_support/session.py`。

6. **修复清理与性能路径**  
问题引用：F7、F9。  
建议方案：消除 `refresh_tools` 的双重 `list_tools()`；为 chat stream 断开补取消；CLI 退出统一 `disconnect_all()`；shutdown 清理失败记录日志但不覆盖主异常。  
预估改动范围：`backend/core/s02_tools/mcp/server_manager.py`、`backend/api/routes/chat_completions.py`、`backend/api/app.py`、`backend/cli.py`。

7. **补齐 MCP 回归测试矩阵**  
问题引用：F12。  
建议方案：至少补 8 类测试：连接失败回滚、超时、server 崩溃、并发 connect、HTTP add/remove API、websocket stale registry、CLI cleanup、权限阻断。  
预估改动范围：`backend/tests/unit/`、`backend/tests/integration/`。

### P2（可以修）

8. **补 transport/config/result 的规范对齐**  
问题引用：F10、F11。  
建议方案：增加 transport 级验证，支持 richer tool result、Resources/Prompts、日志与 Streamable HTTP。  
预估改动范围：`backend/common/types/mcp.py`、`backend/core/s02_tools/mcp/client.py`、`backend/core/s02_tools/mcp/tool_bridge.py`、API/前端展示层。

