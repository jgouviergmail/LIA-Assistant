"""Skill activation — L2 content delivery with structured wrapping.

Per agentskills.io client implementation guide (Step 4):
- Wrap skill content in <skill_content> tags for identification
- List bundled resources (scripts/, references/, assets/) without loading them
- Include skill directory path for relative path resolution
- Used by both activate_skill tool and response_node pre-injection
"""

import re
from pathlib import Path

from src.infrastructure.observability.logging import get_logger

logger = get_logger(__name__)


def activate_skill(skill_name: str, user_id: str | None = None) -> str | None:
    """Activate a skill: return L2 content with structured wrapping.

    Per standard Step 4:
    - Strip frontmatter (body only)
    - Wrap in <skill_content> tags
    - List bundled resources in <skill_resources>
    - Include skill directory for relative path resolution

    Returns None if skill not found.
    """
    from src.domains.skills.cache import SkillsCache

    skill = (
        SkillsCache.get_by_name_for_user(skill_name, user_id)
        if user_id
        else SkillsCache.get_by_name(skill_name)
    )
    if not skill:
        return None

    # Build structured content per standard
    skill_dir = str(Path(skill["source_path"]).parent)
    lines = [f'<skill_content name="{skill["name"]}">']
    lines.append(skill["instructions"])
    lines.append("")
    lines.append(f"Skill directory: {skill_dir}")
    lines.append("Relative paths in this skill are relative to the skill directory.")

    # List bundled resources without loading them (per standard L2)
    # Use all_resources (full recursive discovery), fallback to standard dirs
    resources: list[str] = list(skill.get("all_resources") or [])
    if not resources:
        for script in skill.get("scripts", []):
            resources.append(f"scripts/{script}")
        for ref in skill.get("references", []):
            resources.append(f"references/{ref}")
        for asset in skill.get("assets", []):
            resources.append(f"assets/{asset}")

    if resources:
        lines.append("")
        lines.append("<skill_resources>")
        lines.append("  Use read_skill_resource tool to load any of these files.")
        for r in resources:
            lines.append(f"  <file>{r}</file>")
        lines.append("</skill_resources>")

    lines.append("</skill_content>")

    logger.info("skill_activated", skill_name=skill_name, user_id=user_id)
    return "\n".join(lines)


def get_activated_skill_names(skills_context: str) -> set[str]:
    """Extract activated skill names from context for deduplication."""
    return set(re.findall(r'<skill_content name="([^"]+)">', skills_context))
