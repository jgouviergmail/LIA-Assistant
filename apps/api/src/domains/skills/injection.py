"""Skills prompt injection — L1 catalogue.

Per agentskills.io client implementation guide (Step 3):
- Build XML catalogue with name + description + location
- ~50-100 tokens/skill, negligible overhead for <50 skills
- Include behavioral instructions for activation
- Hide filtered skills entirely (disable-model-invocation)
- Omit section entirely when no skills available
"""

from xml.sax.saxutils import escape as xml_escape

from src.infrastructure.observability.logging import get_logger

logger = get_logger(__name__)


def _is_skill_visible_to_agent(skill: dict, agent_type: str) -> bool:
    """Check if a skill is visible to the given agent type.

    Visibility rules (F6 — declarative agent-visibility in SKILL.md):
    - No agent_visibility field → visible to all (backward compatible)
    - agent_visibility list + visibility_mode=include → visible only to listed types
    - agent_visibility list + visibility_mode=exclude → visible to all except listed

    Args:
        skill: Skill dict with optional agent_visibility and visibility_mode fields.
        agent_type: Agent type to check (sub-agent name or "principal").
    """
    visibility = skill.get("agent_visibility")
    if not visibility:
        return True

    if isinstance(visibility, str):
        visibility = [visibility]

    mode = skill.get("visibility_mode", "include")
    agent_types = set(visibility)

    if mode == "include":
        return agent_type in agent_types
    elif mode == "exclude":
        return agent_type not in agent_types

    return True


def build_skills_catalog(
    user_id: str,
    active_skills: set[str] | None = None,
    agent_type: str | None = None,
) -> str:
    """Build L1 XML catalogue for the planner/response prompt.

    Per standard: includes name, description, location (path to SKILL.md).
    Returns empty string if no skills → zero token overhead (per spec: omit entirely).

    Args:
        user_id: Current user ID.
        active_skills: Set of active skill names for this user (from active_skills_ctx).
            When None, all skills pass (backward compat for contexts without preferences).
        agent_type: Agent type for visibility filtering (None = principal agent, no filter).
    """
    from src.domains.skills.cache import SkillsCache

    skills = SkillsCache.get_for_user(user_id)
    if not skills:
        return ""

    # Filter: only active skills, hide disable-model-invocation
    visible = [
        s
        for s in skills
        if not s.get("disable_model_invocation")
        and (active_skills is None or s["name"] in active_skills)
    ]

    # F6: Filter by agent visibility if agent_type provided
    if agent_type:
        visible = [s for s in visible if _is_skill_visible_to_agent(s, agent_type)]

    if not visible:
        return ""

    # Build XML catalogue per standard format
    lines = ["<available_skills>"]
    for skill in sorted(visible, key=lambda s: s.get("priority", 50), reverse=True):
        lines.append("  <skill>")
        lines.append(f"    <name>{xml_escape(skill['name'])}</name>")
        lines.append(f"    <description>{xml_escape(skill['description'])}</description>")
        # Canonical location (scope/name/SKILL.md) — never exposes server paths
        location = f"{skill['scope']}/{skill['name']}/SKILL.md"
        lines.append(f"    <location>{xml_escape(location)}</location>")
        if skill.get("compatibility"):
            lines.append(f"    <compatibility>{xml_escape(skill['compatibility'])}</compatibility>")
        lines.append("  </skill>")
    lines.append("</available_skills>")

    return "\n".join(lines)
