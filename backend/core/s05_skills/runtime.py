from __future__ import annotations

import os
import re

from pydantic import BaseModel, ConfigDict

from backend.adapters.base import LLMAdapter
from backend.adapters.provider_manager import ProviderManager
from backend.common.errors import AgentError
from backend.common.types import AgentConfig, AgentEventHandler, ProviderConfig
from backend.config.settings import Settings
from backend.core.s01_agent_loop import AgentLoop
from backend.core.s02_tools import ToolRegistry
from backend.core.s02_tools.builtin import register_builtin_tools
from backend.core.s02_tools.builtin.bash import create_bash_tool
from backend.core.s02_tools.mcp import MCPServerManager, MCPToolBridge
from backend.core.system_prompt import build_system_prompt
from backend.core.task_queue import TaskQueue

from .mcp_requirements import extract_required_mcp_servers
from .models import AgentCategory, AgentSpec, ToolConfig
from .registry import SpecRegistry

_RECURSIVE_TOOL_NAMES = {"dispatch_agent", "orchestrate_agents", "spawn_agent"}


class AgentRuntimeDeps(BaseModel):
    model_config = ConfigDict(arbitrary_types_allowed=True)
    provider_manager: ProviderManager
    mcp_manager: MCPServerManager
    settings: Settings
    spec_registry: SpecRegistry


class _FilteredBridge:
    def __init__(
        self,
        bridge: MCPToolBridge,
        registry: ToolRegistry,
        allowed_tools: set[str],
        required_mcp_servers: set[str],
    ) -> None:
        self._bridge = bridge
        self._registry = registry
        self._allowed_tools = allowed_tools
        self._required_mcp_servers = required_mcp_servers

    def needs_sync(self) -> bool:
        if not self._required_mcp_servers:
            return False
        return self._bridge.needs_sync()

    async def sync_all(self) -> int:
        try:
            count = 0
            if self._required_mcp_servers:
                count = await self._bridge.sync_servers(self._required_mcp_servers)
            self._prune_disallowed()
            return count
        except AgentError:
            raise
        except Exception as exc:
            raise AgentError("SKILL_RUNTIME_MCP_SYNC_ERROR", str(exc)) from exc

    async def sync_if_needed(self) -> int:
        try:
            if not self.needs_sync():
                return -1
            count = await self._bridge.sync_servers(self._required_mcp_servers)
            self._prune_disallowed()
            return count
        except AgentError:
            raise
        except Exception as exc:
            raise AgentError("SKILL_RUNTIME_MCP_SYNC_ERROR", str(exc)) from exc

    def _prune_disallowed(self) -> None:
        if not self._allowed_tools:
            return
        for definition in list(self._registry.list_definitions()):
            if definition.name not in self._allowed_tools:
                self._registry.remove(definition.name)


class AgentRuntime:
    def __init__(self, deps: AgentRuntimeDeps) -> None:
        self._deps = deps

    async def create_loop(
        self,
        spec: AgentSpec,
        workspace: str = "",
        session_id: str = "",
        model: str = "",
        provider: str = "",
        task_queue: TaskQueue | None = None,
        event_handler: AgentEventHandler | None = None,
        is_sub_agent: bool = False,
    ) -> AgentLoop:
        try:
            resolved_provider = await self._resolve_provider(provider or spec.provider)
            resolved_model = model or spec.model or resolved_provider.default_model
            resolved_model = resolved_model or self._deps.settings.default_model
            resolved_workspace = os.path.abspath(workspace or os.getcwd())
            adapter = await self._deps.provider_manager.get_adapter(resolved_provider.id)
            registry = self._build_registry(
                spec.tools,
                spec.sub_agents.max_depth,
                resolved_workspace,
                adapter,
                resolved_model,
                task_queue,
                event_handler,
                is_sub_agent,
            )
            bridge = _FilteredBridge(
                MCPToolBridge(self._deps.mcp_manager, registry),
                registry,
                set(spec.tools.allowed_tools),
                extract_required_mcp_servers(spec),
            )
            await bridge.sync_all()
            loop = AgentLoop(
                config=AgentConfig(
                    model=resolved_model,
                    provider=resolved_provider.id,
                    system_prompt=self._compose_system_prompt(
                        resolved_workspace,
                        spec.system_prompt,
                    ),
                    session_id=session_id,
                    tools=sorted(tool.name for tool in registry.list_definitions()),
                    max_iterations=spec.max_iterations,
                ),
                adapter=adapter,
                tool_registry=registry,
            )
            setattr(loop, "_bridge", bridge)  # noqa: B010, SLF001
            setattr(loop, "_agent_spec", spec)  # noqa: B010, SLF001
            setattr(loop, "_timeout_seconds", spec.timeout_seconds)  # noqa: B010, SLF001
            return loop
        except AgentError:
            raise
        except Exception as exc:
            raise AgentError("SKILL_RUNTIME_CREATE_LOOP_ERROR", str(exc)) from exc

    async def create_loop_from_id(
        self,
        spec_id: str,
        workspace: str = "",
        session_id: str = "",
        model: str = "",
        provider: str = "",
        task_queue: TaskQueue | None = None,
        event_handler: AgentEventHandler | None = None,
        is_sub_agent: bool = False,
    ) -> AgentLoop:
        try:
            spec = self._deps.spec_registry.get(spec_id)
            if spec is None:
                raise AgentError("SKILL_SPEC_NOT_FOUND", f"Skill spec not found: {spec_id}")
            if not spec.enabled:
                raise AgentError("SKILL_SPEC_DISABLED", f"Skill spec is disabled: {spec_id}")
            return await self.create_loop(
                spec,
                workspace=workspace,
                session_id=session_id,
                model=model,
                provider=provider,
                task_queue=task_queue,
                event_handler=event_handler,
                is_sub_agent=is_sub_agent,
            )
        except AgentError:
            raise
        except Exception as exc:
            raise AgentError("SKILL_RUNTIME_CREATE_FROM_ID_ERROR", str(exc)) from exc

    async def create_loop_inline(
        self,
        role: str,
        system_prompt: str,
        tools: list[str],
        model: str = "",
        workspace: str = "",
        task_queue: TaskQueue | None = None,
        event_handler: AgentEventHandler | None = None,
        is_sub_agent: bool = False,
    ) -> AgentLoop:
        try:
            slug = re.sub(r"[^A-Za-z0-9_-]+", "-", role or "inline-agent")
            slug = slug.strip("-_") or "inline-agent"
            spec = AgentSpec(
                id=f"inline_{slug}"[:64],
                title=role or "Inline Agent",
                category=AgentCategory.ASSISTANT,
                description=role,
                system_prompt=system_prompt,
                model=model,
                tools=ToolConfig(allowed_tools=tools),
                source_path="inline",
            )
            return await self.create_loop(
                spec,
                workspace=workspace,
                task_queue=task_queue,
                event_handler=event_handler,
                is_sub_agent=is_sub_agent,
            )
        except AgentError:
            raise
        except Exception as exc:
            raise AgentError("SKILL_RUNTIME_CREATE_INLINE_ERROR", str(exc)) from exc

    def _build_registry(
        self,
        tools: ToolConfig,
        max_depth: int,
        workspace: str,
        adapter: LLMAdapter,
        model: str,
        task_queue: TaskQueue | None,
        event_handler: AgentEventHandler | None,
        is_sub_agent: bool,
    ) -> ToolRegistry:
        base_registry = ToolRegistry()
        register_builtin_tools(
            base_registry,
            workspace,
            adapter=adapter,
            default_model=model,
            agent_runtime=self,
            spec_registry=self._deps.spec_registry,
            task_queue=task_queue,
            event_handler=event_handler,
            is_sub_agent=is_sub_agent,
        )
        filtered = ToolRegistry()
        for definition in base_registry.list_definitions():
            if tools.allowed_tools and definition.name not in tools.allowed_tools:
                continue
            if max_depth <= 0 and definition.name in _RECURSIVE_TOOL_NAMES:
                continue
            override = tools.tool_overrides.get(definition.name, {})
            registered = base_registry.get(definition.name)
            if registered is None:
                continue
            _, executor = registered
            if definition.name == "Bash" and isinstance(override.get("timeout"), int):
                filtered.register(*create_bash_tool(workspace, timeout=int(override["timeout"])))
                continue
            filtered.register(definition, executor)
        return filtered

    async def _resolve_provider(self, requested: str) -> ProviderConfig:
        providers = await self._deps.provider_manager.list_all()
        if not providers:
            raise AgentError("SKILL_PROVIDER_MISSING", "No provider configured")
        if requested:
            for provider in providers:
                if provider.id == requested or provider.provider_type.value == requested:
                    return provider
            raise AgentError("SKILL_PROVIDER_NOT_FOUND", f"Provider not found: {requested}")
        default_provider = await self._deps.provider_manager.get_default()
        return default_provider or providers[0]

    @staticmethod
    def _compose_system_prompt(workspace: str, spec_prompt: str) -> str:
        return "\n\n".join(
            part for part in [build_system_prompt(workspace), spec_prompt.strip()] if part
        )


__all__ = ["AgentRuntime", "AgentRuntimeDeps"]
