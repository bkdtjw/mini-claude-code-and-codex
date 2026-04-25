from __future__ import annotations

from backend.adapters.provider_manager import ProviderManager
from backend.common.errors import AgentError
from backend.config.settings import Settings
from backend.core.s02_tools.mcp import MCPServerManager
from backend.core.s05_skills import AgentRuntime, AgentRuntimeDeps, SkillLoader, SpecRegistry


async def init_agent_runtime(
    provider_manager: ProviderManager,
    mcp_manager: MCPServerManager,
    settings: Settings,
) -> tuple[SpecRegistry, AgentRuntime]:
    try:
        spec_registry = SpecRegistry()
        for spec in SkillLoader().load_all():
            spec_registry.register(spec)
        return spec_registry, AgentRuntime(
            AgentRuntimeDeps(
                provider_manager=provider_manager,
                mcp_manager=mcp_manager,
                settings=settings,
                spec_registry=spec_registry,
            )
        )
    except AgentError:
        raise
    except Exception as exc:  # noqa: BLE001
        raise AgentError("AGENT_RUNTIME_INIT_ERROR", str(exc)) from exc


__all__ = ["init_agent_runtime"]
