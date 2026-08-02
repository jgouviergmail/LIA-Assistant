"""Pure predicates over an ExecutionPlan — no LLM, no I/O.

Extracted from ``semantic_validator`` (file-size ratchet): these answer
"what does this plan do?" so the validator can decide whether an LLM review is
worth its token cost. They are deterministic and tolerate both the object and
the dict-serialized plan form (LangGraph state round-trips).
"""

from __future__ import annotations

import re
from collections.abc import Iterator
from typing import TYPE_CHECKING, Any

from src.infrastructure.observability.logging import get_logger

logger = get_logger(__name__)

if TYPE_CHECKING:
    from src.domains.agents.orchestration.plan_schemas import ExecutionPlan

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


def _declared_mutation_flag(tool_name: str) -> bool | None:
    """Mutation flag taken from an EXPLICITLY declared catalogue category.

    Args:
        tool_name: Tool name to look up in the global catalogue.

    Returns:
        ``True``/``False`` when the tool's manifest declares ``tool_category``
        (hand-written ground truth), ``None`` when the tool has no manifest or
        its category is merely inferred from the name — in which case the caller
        falls back to the name heuristic rather than trusting a second guess.
    """
    from src.domains.agents.registry import get_global_registry
    from src.domains.agents.registry.catalogue import ToolManifestNotFound, is_read_only_tool

    try:
        manifest = get_global_registry().get_tool_manifest(tool_name)
    except ToolManifestNotFound:
        return None

    if manifest.tool_category is None:
        return None
    return not is_read_only_tool(manifest)


def tool_is_mutation(tool_name: str) -> bool:
    """Check if a tool performs a mutation operation.

    An explicitly declared catalogue category WINS over ``MUTATION_TOOL_PATTERNS``:
    the patterns are only a heuristic for tools without a manifest, and they
    missed declared mutations whose names carry none of the nine verbs —
    ``cancel_reminder_tool`` (category "delete"), ``edit_image`` and
    ``generate_image`` (category "create"). Being classified read-only removed
    them from the invalid-mutation-plan safety net in ``semantic_validator_node``,
    so an unconverged plan calling them was executed instead of being rerouted
    to a HITL clarification.

    Args:
        tool_name: Tool name to classify.

    Returns:
        True when the tool mutates data (declared category, else name pattern).
    """
    declared = _declared_mutation_flag(tool_name)
    if declared is not None:
        return declared

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


#: Sentinel telling "the analyzer said nothing" apart from "the analyzer said
#: False". They are NOT the same verdict, and only the second one is evidence.
_ABSENT = object()


def plan_writes_without_write_intent(plan: Any, query_intelligence: Any) -> list[str]:
    """Mutation tools a plan calls while the ANALYZER read no intent to write.

    The mirror image of the "mutation intent but no mutation tool" rule: that
    one catches a plan that under-delivers, this one a plan that acts when
    nobody asked it to. Production 2026-08-01: "de quand date mon dernier appel
    à ma femme ?" produced ``get_contacts_tool`` then ``place_phone_call_tool``
    with objective "vérifier la date du dernier appel" — the user asked WHEN,
    the plan was to phone her and ask. Tool-level HITL would still have required
    a click, but a read question that surfaces "confirm this call?" has already
    broken the user's trust.

    Deliberately conservative on the two axes that could produce noise:

    - it needs an EXPLICIT ``is_mutation_intent=False`` from the analyzer; no
      verdict means no contradiction, so an absent intelligence never fires;
    - it reads the declared tool category (``tool_is_mutation``), so a tool
      whose name carries no CRUD verb — ``place_phone_call_tool`` — is still
      recognised as a write.

    Args:
        plan: ExecutionPlan, its dict form, or None.
        query_intelligence: QueryIntelligence or its dict form, or None.

    Returns:
        The offending tool names in step order — empty when the plan is
        consistent with the detected intent.
    """
    if query_intelligence is None:
        return []
    # `_ABSENT`, not `False`: a payload that carries NO verdict says nothing
    # about intent, and defaulting it to False would read that silence as "the
    # user only wanted to read" — sending every legitimate action back to the
    # planner. Only an explicit False may contradict a writing plan.
    if isinstance(query_intelligence, dict):
        verdict = query_intelligence.get("is_mutation_intent", _ABSENT)
    else:
        verdict = getattr(query_intelligence, "is_mutation_intent", _ABSENT)
    if verdict is _ABSENT or verdict:
        return []
    return [tool for tool in _iter_plan_tools(plan) if tool_is_mutation(tool)]


def plan_covers_domain(plan: Any, domain: str) -> bool:
    """Tell whether any step of ``plan`` calls a tool of ``domain``.

    The tool's domain comes from its MANIFEST (agent + ``serves_domains``), not
    from its name. Deriving it from the name made ``place_phone_call_tool``
    — whose name starts with ``place_`` — belong to ``places`` and NOT to
    ``telephony``, so the "primary_domain_uncovered" rule fired on every
    single-step call request while staying silent on the plan that genuinely
    dropped the domain (prod 2026-08-01).

    The name convention survives as the fallback for tools with no manifest,
    via ``get_result_key_for_tool``.

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
        from src.domains.agents.registry.tool_domain_resolution import tool_serves_domain

        expected_key = get_result_key(domain)
        if not expected_key:
            return True

        resolved_any = False
        for tool in _iter_plan_tools(plan):
            declared = tool_serves_domain(tool, domain)
            if declared is not None:
                resolved_any = True
                if declared:
                    return True
                continue

            # No manifest: fall back to the name convention.
            tool_key = get_result_key_for_tool(tool)
            if tool_key is None:
                # Unresolvable tool: it cannot be proven to miss the domain,
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


# Emails on RFC 2606 reserved domains (example.com/org/net, .invalid, .test) are
# ALWAYS fabricated — no real mailbox can live there. Observed in prod
# (2026-07-17): the planner filled attendees=['jane.doe@example.com'] for
# a real contact instead of resolving or omitting. The reserved TLDs are only
# matched as the FINAL label (dot required) so real domains like test.com or
# invalid-prefixed names never false-positive.
_PLACEHOLDER_EMAIL_RE = re.compile(
    r"@(?:[\w-]+\.)*example\.(?:com|org|net)\b|@[\w.-]+\.(?:invalid|test)\b",
    re.IGNORECASE,
)

# Free-text parameters where a placeholder address may be QUOTED legitimately
# (e.g. a dictated email body citing example.com) — never flagged.
_FREE_TEXT_PARAM_NAMES = frozenset(
    {"body", "subject", "description", "notes", "content_instruction", "message", "text", "content"}
)


def _iter_param_strings(value: Any) -> Iterator[str]:
    """Yield every string nested inside a parameter value (str/list/dict)."""
    if isinstance(value, str):
        yield value
    elif isinstance(value, list | tuple):
        for item in value:
            yield from _iter_param_strings(item)
    elif isinstance(value, dict):
        for item in value.values():
            yield from _iter_param_strings(item)


def detect_placeholder_contacts(plan: ExecutionPlan) -> list[str]:
    """Find fabricated placeholder emails in MUTATION step parameters.

    Deterministic pre-LLM guard: scans every non-free-text parameter of
    mutation steps for RFC 2606 reserved-domain emails. Read-only steps are
    exempt (no real-world damage, and a search query quoting a placeholder
    must not loop the planner).

    Returns:
        Human-readable findings like ``"step_1.attendees='j.doe@example.com'"``
        (empty list when the plan is clean).
    """
    findings: list[str] = []
    for step in plan.steps:
        if not tool_is_mutation(step.tool_name or ""):
            continue
        for param_name, value in (step.parameters or {}).items():
            if param_name.lower() in _FREE_TEXT_PARAM_NAMES:
                continue
            for text in _iter_param_strings(value):
                if _PLACEHOLDER_EMAIL_RE.search(text):
                    findings.append(f"{step.step_id}.{param_name}='{text[:60]}'")
    return findings


__all__ = [
    "CROSS_DOMAIN_CAPABLE_TOOLS",
    "MUTATION_TOOL_PATTERNS",
    "detect_placeholder_contacts",
    "plan_contains_mutation",
    "plan_writes_without_write_intent",
    "plan_covers_domain",
    "tool_is_mutation",
]
