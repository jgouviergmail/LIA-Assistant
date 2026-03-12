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


def build_skills_catalog(
    user_id: str,
    disabled_skills: set[str] | None = None,
) -> str:
    """Build L1 XML catalogue for the planner/response prompt.

    Per standard: includes name, description, location (path to SKILL.md).
    Returns empty string if no skills → zero token overhead (per spec: omit entirely).

    Args:
        user_id: Current user ID.
        disabled_skills: Set of skill names disabled by the user (from user.disabled_skills).
    """
    from src.domains.skills.cache import SkillsCache

    skills = SkillsCache.get_for_user(user_id)
    if not skills:
        return ""

    disabled = disabled_skills or set()

    # Filter: hide disabled + disable-model-invocation skills entirely
    visible = [
        s for s in skills if not s.get("disable_model_invocation") and s["name"] not in disabled
    ]
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
