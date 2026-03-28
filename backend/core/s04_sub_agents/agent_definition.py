from __future__ import annotations

from pathlib import Path

from pydantic import BaseModel, Field

from backend.common.errors import AgentError


class AgentRole(BaseModel):
    """Definition of a sub-agent role."""

    name: str
    description: str = ""
    system_prompt: str
    allowed_tools: list[str] = Field(default_factory=list)
    max_iterations: int = 10
    model: str = ""


class AgentDefinitionLoader:
    """Load agent role definitions from agents/builtin."""

    def __init__(self, agents_dir: str | None = None) -> None:
        base_dir = Path(__file__).resolve().parents[3] / "agents" / "builtin"
        self._agents_dir = Path(agents_dir) if agents_dir else base_dir

    def load_role(self, role_name: str) -> AgentRole | None:
        try:
            role_path = self._resolve_role_path(role_name)
            if role_path is None:
                return None
            raw = role_path.read_text(encoding="utf-8").strip()
            if not raw:
                return None
            config, body = self._split_frontmatter(raw)
            return AgentRole(
                name=str(config.get("name", role_name)),
                description=str(config.get("description", "")),
                system_prompt=body.strip(),
                allowed_tools=list(config.get("allowed_tools", [])),
                max_iterations=int(config.get("max_iterations", 10)),
                model=str(config.get("model", "")),
            )
        except AgentError:
            raise
        except Exception as exc:
            raise AgentError("SUB_AGENT_LOAD_ROLE_ERROR", str(exc)) from exc

    def list_roles(self) -> list[str]:
        try:
            roles: set[str] = set()
            if not self._agents_dir.exists():
                return []
            for entry in self._agents_dir.iterdir():
                if entry.is_dir() and (entry / "agent.md").exists():
                    roles.add(entry.name)
                if entry.is_file() and entry.suffix == ".md":
                    roles.add(entry.stem)
            return sorted(roles)
        except Exception as exc:
            raise AgentError("SUB_AGENT_LIST_ROLES_ERROR", str(exc)) from exc

    def _resolve_role_path(self, role_name: str) -> Path | None:
        folder_path = self._agents_dir / role_name / "agent.md"
        file_path = self._agents_dir / f"{role_name}.md"
        if folder_path.exists():
            return folder_path
        if file_path.exists():
            return file_path
        return None

    def _split_frontmatter(self, raw: str) -> tuple[dict[str, object], str]:
        if not raw.startswith("---"):
            return {}, raw
        lines = raw.splitlines()
        end_index = next((index for index in range(1, len(lines)) if lines[index].strip() == "---"), -1)
        if end_index < 0:
            return {}, raw
        frontmatter = self._parse_frontmatter(lines[1:end_index])
        body = "\n".join(lines[end_index + 1 :])
        return frontmatter, body

    def _parse_frontmatter(self, lines: list[str]) -> dict[str, object]:
        parsed: dict[str, object] = {}
        for line in lines:
            if ":" not in line:
                continue
            key, value = line.split(":", 1)
            parsed[key.strip()] = self._coerce_value(value.strip())
        return parsed

    def _coerce_value(self, value: str) -> object:
        if value.startswith("[") and value.endswith("]"):
            items = [item.strip().strip("\"'") for item in value[1:-1].split(",") if item.strip()]
            return items
        if value.isdigit():
            return int(value)
        return value.strip("\"'")


__all__ = ["AgentDefinitionLoader", "AgentRole"]
