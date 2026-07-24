"""Pure predicates over an ExecutionPlan — no LLM, no I/O.

Extracted from ``semantic_validator`` (file-size ratchet): these answer
"what does this plan do?" so the validator can decide whether an LLM review is
worth its token cost. They are deterministic and tolerate both the object and
the dict-serialized plan form (LangGraph state round-trips).
"""

from __future__ import annotations

from typing import Any

from src.infrastructure.observability.logging import get_logger

logger = get_logger(__name__)

# Tool name patterns indicating mutation operations (for tool validation ONLY)
# These match against TOOL NAMES (internal data), not user queries
# Used to verify plan has correct mutation tool when user requests mutation
MUTATION_TOOL_PATTERNS = [
    "create",
    "update",
    "delete",
    "send",
    "reply",
    "forward",
    "remove",
    "add",
    "modify",
]

# ============================================================================
# FIX 2026-01-11: Tools with cross-domain capabilities
# ============================================================================
# These tools handle multiple domains intrinsically (e.g., send_email resolves
# contacts automatically via the HITL flow). A single-step plan with one of
# these tools is valid even when 2+ domains are expected.
#
# Example: "send an email to john" → domains=['emails', 'contacts']
# Plan: [send_email_draft] → Valid! The tool resolves contact via draft+HITL.
# Without this fix: semantic_validator forces re-planning → +9k tokens wasted.
# ============================================================================
CROSS_DOMAIN_CAPABLE_TOOLS = frozenset(
    [
        # Email tools that can resolve contacts via semantic_type="email_address"
        "send_email_tool",
        "send_email_draft",
        "reply_email_tool",
        "reply_email_draft",
        "forward_email_tool",
        "forward_email_draft",
        # Event tools that can resolve attendees from contacts
        "create_event_tool",
        "create_event_draft",
        "update_event_tool",
        "update_event_draft",
    ]
)


def _iter_plan_tools(plan: Any) -> list[str]:
    """List the tool names of a plan, tolerating None / object / dict forms.

    Args:
        plan: ExecutionPlan, its dict form, or None.

    Returns:
        Tool names in step order (steps without a tool are skipped).
    """
    if plan is None:
        return []
    steps = getattr(plan, "steps", None)
    if steps is None and isinstance(plan, dict):
        steps = plan.get("steps")
    tools: list[str] = []
    for step in steps or []:
        tool = getattr(step, "tool_name", None)
        if tool is None and isinstance(step, dict):
            tool = step.get("tool_name")
        if tool:
            tools.append(tool)
    return tools


def tool_is_mutation(tool_name: str) -> bool:
    """Check if a tool name indicates a mutation operation.

    Args:
        tool_name: Tool name to classify.

    Returns:
        True when the name carries a mutation pattern.
    """
    tool_lower = tool_name.lower()
    return any(pattern in tool_lower for pattern in MUTATION_TOOL_PATTERNS)


def plan_contains_mutation(plan: Any) -> bool:
    """True if ANY step of ``plan`` calls a mutation tool.

    Public helper for the safety net that keeps an INVALID mutation plan from
    being executed by the max-iterations bypass (it is rerouted to a HITL
    clarification instead). Tolerates None and the dict-serialized plan form.

    Args:
        plan: ExecutionPlan, its dict form, or None.

    Returns:
        True when at least one step mutates.
    """
    return any(tool_is_mutation(tool) for tool in _iter_plan_tools(plan))


def plan_covers_domain(plan: Any, domain: str) -> bool:
    """Tell whether any step of ``plan`` calls a tool of ``domain``.

    Both sides are resolved through ``DOMAIN_REGISTRY`` (the single source of
    truth for the domain vocabulary) rather than by name heuristics: the domain
    is mapped to its ``result_key`` and compared with the ``result_key`` the
    registry derives for each step's tool.

    Fail-open: an unknown domain, a plan whose tools are all unregistered (MCP,
    skills, future tools) or any registry error answers True, so the caller
    never acts on coverage it could not establish.

    Args:
        plan: ExecutionPlan (or its dict form) to inspect.
        domain: Domain name from QueryIntelligence (e.g. "weather").

    Returns:
        True when the plan touches the domain, or when coverage cannot be
        established.
    """
    try:
        from src.domains.agents.registry.domain_taxonomy import (
            get_result_key,
            get_result_key_for_tool,
        )

        expected_key = get_result_key(domain)
        if not expected_key:
            return True

        resolved_any = False
        for tool in _iter_plan_tools(plan):
            tool_key = get_result_key_for_tool(tool)
            if tool_key is None:
                # Unregistered tool: it cannot be proven to miss the domain,
                # so it must not count as evidence either way.
                continue
            resolved_any = True
            if tool_key == expected_key:
                return True

        # Nothing resolvable in the plan -> no evidence: fail open.
        return not resolved_any
    except Exception as exc:
        logger.debug(
            "plan_domain_coverage_check_failed_open",
            domain=domain,
            error=str(exc),
            error_type=type(exc).__name__,
        )
        return True


__all__ = [
    "CROSS_DOMAIN_CAPABLE_TOOLS",
    "MUTATION_TOOL_PATTERNS",
    "plan_contains_mutation",
    "plan_covers_domain",
    "tool_is_mutation",
]
