from __future__ import annotations

import re
from enum import Enum
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, field_validator

_SPEC_ID_PATTERN = re.compile(r"^[A-Za-z0-9_-]{1,64}$")


class AgentCategory(str, Enum):
    CODING = "coding"
    CHAT = "chat"
    RESEARCH = "research"
    AGGREGATION = "aggregation"
    DOCUMENT = "document"
    ASSISTANT = "assistant"


class SubAgentPolicy(BaseModel):
    allowed_specs: list[str] = Field(default_factory=list)
    max_concurrent: int = Field(default=5, ge=1)
    max_depth: int = Field(default=1, ge=0)


class ToolConfig(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    allowed_tools: list[str] = Field(default_factory=list)
    tool_overrides: dict[str, dict[str, Any]] = Field(
        default_factory=dict,
        alias="tool_config",
    )


class AgentSpec(BaseModel):
    id: str
    title: str
    category: AgentCategory
    description: str = ""
    system_prompt: str = ""
    model: str = ""
    provider: str = ""
    max_iterations: int = Field(default=20, ge=1)
    timeout_seconds: float = Field(default=300.0, ge=10.0)
    enabled: bool = True
    tools: ToolConfig = Field(default_factory=ToolConfig)
    sub_agents: SubAgentPolicy = Field(default_factory=SubAgentPolicy)
    source_path: str = ""

    @field_validator("id")
    @classmethod
    def validate_id(cls, value: str) -> str:
        if not _SPEC_ID_PATTERN.fullmatch(value):
            raise ValueError("id must match [A-Za-z0-9_-]{1,64}")
        return value


__all__ = [
    "AgentCategory",
    "AgentSpec",
    "SubAgentPolicy",
    "ToolConfig",
]
