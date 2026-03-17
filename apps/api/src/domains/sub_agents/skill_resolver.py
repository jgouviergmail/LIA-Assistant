"""
Sub-Agent skill and tool resolution.

Resolves which skills and tools a sub-agent has access to,
and builds the complete system prompt with read-only constraints.
"""

import structlog

from src.domains.sub_agents.constants import (
    SUBAGENT_CONTEXT_SUMMARY_PREFIX,
    SUBAGENT_READ_ONLY_PREFIX,
)

logger = structlog.get_logger(__name__)


def resolve_tools_for_subagent(
    allowed_tools: list[str],
    blocked_tools: list[str],
    all_tools: list,
) -> list:
    """Filter tools based on sub-agent's allowed/blocked configuration.

    The sub_agent_tools themselves are always excluded (depth=1 enforcement).

    Args:
        allowed_tools: Tool whitelist (empty = all except blocked).
        blocked_tools: Tool blacklist (V1 templates include all write tools).
        all_tools: Full list of available BaseTool instances.

    Returns:
        Filtered list of BaseTool instances.
    """
    # Sub-agent tools are always excluded to prevent recursive spawning
    sub_agent_tool_names = {
        "list_sub_agents_tool",
        "execute_sub_agent_tool",
        "create_sub_agent_tool",
        "get_sub_agent_results_tool",
    }

    blocked = set(blocked_tools) | sub_agent_tool_names
    allowed = set(allowed_tools) if allowed_tools else None

    filtered = []
    for tool in all_tools:
        tool_name = getattr(tool, "name", "")
        if tool_name in blocked:
            continue
        if allowed and tool_name not in allowed:
            continue
        filtered.append(tool)

    logger.debug(
        "subagent_tools_resolved",
        total_available=len(all_tools),
        filtered_count=len(filtered),
        blocked_count=len(blocked),
    )

    return filtered


def build_subagent_system_prompt(
    system_prompt: str,
    personality_instruction: str | None = None,
    context_instructions: str | None = None,
    last_execution_summary: str | None = None,
    skills_context: str = "",
) -> str:
    """Assemble the complete sub-agent system prompt.

    Structure:
    1. Read-only prefix (V1 constraint)
    2. Custom system prompt (from sub-agent config)
    3. Personality instruction (if any)
    4. Skills L2 context (if any)
    5. Context instructions (if any)
    6. Last execution summary (continuity)

    Args:
        system_prompt: Sub-agent's custom instructions.
        personality_instruction: Optional personality override.
        context_instructions: Additional context.
        last_execution_summary: Summary from previous execution.
        skills_context: Compiled L2 skills text.

    Returns:
        Complete system prompt string.
    """
    parts = [SUBAGENT_READ_ONLY_PREFIX, system_prompt]

    if personality_instruction:
        parts.append(f"\n{personality_instruction}")

    if skills_context:
        parts.append(f"\n{skills_context}")

    if context_instructions:
        parts.append(f"\n{context_instructions}")

    if last_execution_summary:
        parts.append(f"\n{SUBAGENT_CONTEXT_SUMMARY_PREFIX}{last_execution_summary}")

    return "\n".join(parts)


def resolve_skills_context(
    skill_ids: list[str],
    user_id: str,
    agent_type: str,
) -> str:
    """Resolve and compile L2 skills context for a sub-agent.

    Loads skills from cache, filters by agent_type visibility,
    and activates L2 content for each.

    Args:
        skill_ids: Skill IDs assigned to this sub-agent.
        user_id: Owner user ID.
        agent_type: Sub-agent name/type for visibility filtering.

    Returns:
        Compiled L2 skills text (may be empty).
    """
    if not skill_ids:
        return ""

    from src.domains.skills.cache import SkillsCache

    skills = SkillsCache.get_for_user(user_id)
    if not skills:
        return ""

    skill_map = {s["name"]: s for s in skills}
    activated_parts = []

    for skill_id in skill_ids:
        skill = skill_map.get(skill_id)
        if not skill:
            logger.warning(
                "subagent_skill_not_found",
                skill_id=skill_id,
                user_id=user_id,
                agent_type=agent_type,
            )
            continue

        # Check visibility
        if not is_skill_visible_to_agent(skill, agent_type):
            continue

        instructions = skill.get("instructions", "")
        if instructions:
            activated_parts.append(f"## Skill: {skill['name']}\n{instructions}")

    if not activated_parts:
        return ""

    logger.debug(
        "subagent_skills_resolved",
        agent_type=agent_type,
        skill_count=len(activated_parts),
    )

    return "\n\n".join(activated_parts)


def is_skill_visible_to_agent(skill: dict, agent_type: str) -> bool:
    """Check if a skill is visible to the given agent type.

    Delegates to the canonical implementation in skills.injection to avoid
    duplication (DRY). See _is_skill_visible_to_agent() in injection.py
    for the full visibility rules documentation.

    Args:
        skill: Skill dict with optional agent_visibility and visibility_mode fields.
        agent_type: Agent type to check (sub-agent name or "principal").

    Returns:
        True if the skill is visible to this agent type.
    """
    from src.domains.skills.injection import _is_skill_visible_to_agent

    return _is_skill_visible_to_agent(skill, agent_type)
