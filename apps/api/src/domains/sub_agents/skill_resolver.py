"""Sub-agent tool & skill resolution.

After ADR-083 Phase 2 cleanup, this module only provides what the ephemeral
planner-delegation path (`delegate_to_sub_agent_tool` → `ReactSubAgentRunner`)
still needs:

- `resolve_tools_for_subagent`: filter the tool registry down to a read-only
  subset for the ReAct sub-agent loop (excludes the delegate tool itself,
  anti-recursion).
- `is_skill_visible_to_agent`: thin re-export of the canonical visibility
  check used by both the principal agent and (transitively) any skill-aware
  sub-agent prompt builder a caller may wire up.

The previous `build_subagent_system_prompt` and `resolve_skills_context`
helpers were tied to the removed `SubAgentExecutor` and are gone.
"""

import structlog

from src.core.constants import TOOL_NAME_DELEGATE_SUB_AGENT

logger = structlog.get_logger(__name__)


def resolve_tools_for_subagent(
    allowed_tools: list[str],
    blocked_tools: list[str],
    all_tools: list,
) -> list:
    """Filter tools based on sub-agent's allowed/blocked configuration.

    The sub-agent meta-tools and `delegate_to_sub_agent_tool` itself are
    always excluded (anti-recursion / depth=1 enforcement).

    Args:
        allowed_tools: Tool whitelist (empty = all except blocked).
        blocked_tools: Tool blacklist (caller typically passes
            `SUBAGENT_DEFAULT_BLOCKED_TOOLS`).
        all_tools: Full list of available BaseTool instances.

    Returns:
        Filtered list of BaseTool instances.
    """
    # Sub-agent tools are always excluded to prevent recursive spawning.
    # `delegate_to_sub_agent_tool` is the one a sub-agent's ReAct loop would
    # be most tempted to call (ADR-083). Excluding it here is the primary
    # anti-recursion mechanism — the session_id/thread_id depth check in
    # `delegate_to_sub_agent_tool` itself is belt-and-suspenders.
    sub_agent_tool_names = {
        "list_sub_agents_tool",
        "execute_sub_agent_tool",
        "create_sub_agent_tool",
        "get_sub_agent_results_tool",
        TOOL_NAME_DELEGATE_SUB_AGENT,
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


def is_skill_visible_to_agent(skill: dict, agent_type: str) -> bool:
    """Check if a skill is visible to the given agent type.

    Delegates to the canonical implementation in skills.injection to avoid
    duplication (DRY). See `_is_skill_visible_to_agent()` in injection.py
    for the full visibility rules documentation.

    Args:
        skill: Skill dict with optional agent_visibility and visibility_mode
            fields.
        agent_type: Agent type to check (sub-agent name or "principal").

    Returns:
        True if the skill is visible to this agent type.
    """
    from src.domains.skills.injection import _is_skill_visible_to_agent

    return _is_skill_visible_to_agent(skill, agent_type)
