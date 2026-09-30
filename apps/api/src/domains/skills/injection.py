"""Skills prompt injection — the L1 catalogues.

Per agentskills.io client implementation guide (Step 3):
- Build XML catalogue with name + description + location
- ~50-100 tokens/skill, negligible overhead for <50 skills
- Include behavioral instructions for activation
- Hide filtered skills entirely (disable-model-invocation)
- Omit section entirely when no skills available

A third-party skill (ADR-327) is marked in both catalogues, the catalogue says
what the mark means, and its declared priority is ignored: a description
written elsewhere never outranks the others.
"""

from typing import Any
from xml.sax.saxutils import escape as xml_escape

from src.domains.skills.trust import is_third_party, trust_lines
from src.infrastructure.observability.logging import get_logger

logger = get_logger(__name__)

#: The priority every third-party entry sorts at, whatever it declares.
_THIRD_PARTY_PRIORITY = 50


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


def _visible_skills(
    user_id: str,
    active_skills: set[str] | None,
    agent_type: str | None = None,
) -> list[dict[str, Any]]:
    """The skills a catalogue may show: resolved for the person, active, invocable.

    Args:
        user_id: Current user ID.
        active_skills: Active names for this request (None: every skill passes).
        agent_type: Agent type for visibility filtering (None: no filter).

    Returns:
        The visible cache entries.
    """
    from src.domains.skills.cache import SkillsCache

    visible = [
        s
        for s in SkillsCache.get_for_user(user_id)
        if not s.get("disable_model_invocation")
        and (active_skills is None or s["name"] in active_skills)
    ]
    if agent_type:
        visible = [s for s in visible if _is_skill_visible_to_agent(s, agent_type)]
    return visible


def _sort_priority(skill: dict[str, Any]) -> int:
    """A skill's catalogue priority; a third-party skill's is neutral."""
    if is_third_party(skill):
        return _THIRD_PARTY_PRIORITY
    return int(skill.get("priority", 50))


def _one_line(text: str) -> str:
    """A description as ONE line: a newline in it must not open a heading or a list."""
    return " ".join(str(text).split())


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
    visible = _visible_skills(user_id, active_skills, agent_type)
    if not visible:
        return ""

    # Build XML catalogue per standard format
    lines = ["<available_skills>"]
    marked = False
    for skill in sorted(visible, key=_sort_priority, reverse=True):
        third_party = is_third_party(skill)
        marked = marked or third_party
        lines.append('  <skill trust="third_party">' if third_party else "  <skill>")
        lines.append(f"    <name>{xml_escape(skill['name'])}</name>")
        lines.append(f"    <description>{xml_escape(skill['description'])}</description>")
        # Canonical location (scope/name/SKILL.md) — never exposes server paths
        location = f"{skill['scope']}/{skill['name']}/SKILL.md"
        lines.append(f"    <location>{xml_escape(location)}</location>")
        if skill.get("compatibility"):
            lines.append(f"    <compatibility>{xml_escape(skill['compatibility'])}</compatibility>")
        lines.append("  </skill>")
    lines.append("</available_skills>")
    if marked:
        lines.append(trust_lines()["catalogue_note"])

    return "\n".join(lines)


def build_analyzer_skill_list(
    user_id: str, active_skills: set[str] | None, *, enabled: bool = True
) -> str:
    """The query analyzer's Markdown list of the skills it may detect.

    Same filtering as :func:`build_skills_catalog`; each description is kept
    on its own line, and a third-party entry is marked.

    Args:
        user_id: Current user ID.
        active_skills: Active names for this request (None: every skill passes).
        enabled: Whether skills are on for this deployment; off reads as none.

    Returns:
        One ``- **name**: description`` line per skill, or the empty sentence.
    """
    visible = _visible_skills(user_id, active_skills) if enabled else []
    lines = trust_lines()
    if not visible:
        return lines["analyzer_empty"]
    rows: list[str] = []
    marked = False
    for skill in visible:
        third_party = is_third_party(skill)
        marked = marked or third_party
        marker = f" ({lines['analyzer_marker']})" if third_party else ""
        rows.append(f"- **{skill['name']}**{marker}: {_one_line(skill['description'])}")
    if marked:
        rows.append(lines["catalogue_note"])
    return "\n".join(rows)
