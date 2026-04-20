from __future__ import annotations

from pathlib import Path

import yaml

from backend.common.errors import AgentError
from backend.common.logging import get_logger

from .models import AgentSpec, SubAgentPolicy, ToolConfig

logger = get_logger(component="skill_loader")


class SkillLoader:
    def __init__(self, skills_dir: str | None = None) -> None:
        base_dir = Path(__file__).resolve().parents[3] / "skills"
        self._skills_dir = Path(skills_dir) if skills_dir else base_dir

    def load_all(self) -> list[AgentSpec]:
        try:
            if not self._skills_dir.exists():
                logger.info("no_skills_found", skills_dir=str(self._skills_dir))
                return []
            specs: list[AgentSpec] = []
            for entry in sorted(self._skills_dir.iterdir()):
                if not entry.is_dir():
                    continue
                spec = self.load_one(entry)
                if spec is not None:
                    specs.append(spec)
            if not specs:
                logger.info("no_skills_found", skills_dir=str(self._skills_dir))
            return specs
        except AgentError:
            raise
        except Exception as exc:
            raise AgentError("SKILL_LOAD_ALL_ERROR", str(exc)) from exc

    def load_one(self, skill_dir: Path) -> AgentSpec | None:
        try:
            skill_file = skill_dir / "SKILL.md"
            if not skill_file.exists():
                return None
            raw = skill_file.read_text(encoding="utf-8").strip()
            config, body = self._split_frontmatter(raw)
            prompt_text = self._read_optional_text(skill_dir / "prompt.md")
            spec = AgentSpec.model_validate(
                {
                    **config,
                    "id": config.get("id") or skill_dir.name,
                    "title": config.get("title") or skill_dir.name,
                    "description": body.strip(),
                    "system_prompt": prompt_text or body.strip(),
                    "tools": ToolConfig.model_validate(self._read_yaml(skill_dir / "tools.yaml")),
                    "sub_agents": SubAgentPolicy.model_validate(
                        self._read_yaml(skill_dir / "sub_agents.yaml")
                    ),
                    "source_path": str(skill_dir.resolve()),
                }
            )
            if spec.id != skill_dir.name:
                raise AgentError(
                    "SKILL_ID_MISMATCH",
                    f"skill id {spec.id!r} does not match directory name {skill_dir.name!r}",
                )
            logger.info("skill_loaded", spec_id=spec.id, source_path=spec.source_path)
            return spec
        except AgentError as exc:
            logger.warning("skill_skipped", skill_dir=str(skill_dir), error=exc.message)
            return None
        except Exception as exc:
            logger.warning("skill_skipped", skill_dir=str(skill_dir), error=str(exc))
            return None

    def _split_frontmatter(self, raw: str) -> tuple[dict[str, object], str]:
        if not raw.startswith("---"):
            return {}, raw
        lines = raw.splitlines()
        end_index = next(
            (index for index in range(1, len(lines)) if lines[index].strip() == "---"),
            -1,
        )
        if end_index < 0:
            return {}, raw
        payload = yaml.safe_load("\n".join(lines[1:end_index])) or {}
        frontmatter = payload if isinstance(payload, dict) else {}
        return frontmatter, "\n".join(lines[end_index + 1 :])

    @staticmethod
    def _read_optional_text(path: Path) -> str:
        if not path.exists():
            return ""
        return path.read_text(encoding="utf-8").strip()

    @staticmethod
    def _read_yaml(path: Path) -> dict[str, object]:
        if not path.exists():
            return {}
        loaded = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
        return loaded if isinstance(loaded, dict) else {}


__all__ = ["SkillLoader"]
