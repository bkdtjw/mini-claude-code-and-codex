from __future__ import annotations

from backend.common.errors import AgentError


class KnowledgeError(AgentError):
    pass


__all__ = ["KnowledgeError"]
