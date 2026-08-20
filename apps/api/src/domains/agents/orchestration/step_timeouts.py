"""Per-tool-family step timeout policy for the parallel executor.

Extracted from ``parallel_executor.py`` (frozen at its size cap) on
2026-08-20, when the web-research family was added: one cohesive unit — the
tool-name groupings and the floor/ceiling arbitration — with no executor
state involved. The helper is intentionally pure (no side effects, no I/O
beyond a single ``get_settings()`` read) so it is testable in isolation:
``tests/unit/domains/agents/orchestration/test_parallel_executor_compute_step_timeout.py``.

Every per-family timeout lives in Settings and is read inside
:func:`compute_step_timeout`, so all of them are ``.env``-tunable:

- sub-agent : ``subagent_tool_timeout_seconds`` / ``subagent_tool_max_timeout_seconds``
- browser   : ``browser_tool_timeout_seconds`` / ``max_browser_tool_timeout_seconds``
- MCP ReAct : ``mcp_react_step_timeout_seconds`` / ``mcp_react_step_max_timeout_seconds``
- image     : ``image_generation_tool_timeout_seconds`` /
  ``max_image_generation_tool_timeout_seconds`` (ADR-160)
- document  : ``document_generation_tool_timeout_seconds`` /
  ``max_document_generation_tool_timeout_seconds`` (ADR-226 — the internal
  LLM writes whole documents, well above 30 s)
- web rsrch : ``web_research_tool_timeout_seconds`` /
  ``max_web_research_tool_timeout_seconds`` (Perplexity-backed synthesis,
  killed at the generic 30 s in prod 2026-08)
- devops    : ``devops_claude_tool_timeout_seconds``, generic ceiling

The image family got its own ceiling on 2026-07-27: a measured 138.3 s
render sat above the generic 120 s cap, so no floor value could have
rescued it.
"""

from __future__ import annotations

from src.core.config import get_settings
from src.core.constants import MCP_ITERATIVE_TASK_SUFFIX

# Tool-name groupings consumed by `compute_step_timeout`. Kept at module
# scope (not inside the helper) so the timeout policy is greppable and the
# constants are evaluated once, not on every step.
_BROWSER_TOOL_NAME = "browser_task_tool"
_DEVOPS_TOOL_NAME = "claude_server_task_tool"
_SUB_AGENT_TOOL_NAME = "delegate_to_sub_agent_tool"
_IMAGE_TOOL_NAMES: frozenset[str] = frozenset({"generate_image", "edit_image"})
_DOCUMENT_TOOL_NAMES: frozenset[str] = frozenset({"generate_document"})
# Web research backed by an external LLM (Perplexity synthesis / unified
# multi-source search): prod 2026-08-14→20 measured these killed at the
# generic 30 s while the synthesis legitimately runs longer.
_WEB_RESEARCH_TOOL_NAMES: frozenset[str] = frozenset(
    {"unified_web_search_tool", "perplexity_search_tool", "perplexity_ask_tool"}
)
_HIGH_LATENCY_TOOL_NAMES: frozenset[str] = (
    _IMAGE_TOOL_NAMES
    | _DOCUMENT_TOOL_NAMES
    | _WEB_RESEARCH_TOOL_NAMES
    | frozenset({_SUB_AGENT_TOOL_NAME, _DEVOPS_TOOL_NAME, _BROWSER_TOOL_NAME})
)


def compute_step_timeout(
    step_tool_name: str | None,
    step_requested_timeout: float | None,
) -> float:
    """Compute the effective timeout (seconds) for an ExecutionStep.

    Implements the per-tool-family policy:

    - ``delegate_to_sub_agent_tool``: floor / ceiling tunable via Settings
      (`subagent_tool_timeout_seconds` / `subagent_tool_max_timeout_seconds`),
      so operators can adjust without touching application-wide constants.
    - ``browser_task_tool``: dedicated higher floor / ceiling
      (`BROWSER_TOOL_TIMEOUT_SECONDS` / `MAX_BROWSER_TOOL_TIMEOUT_SECONDS`)
      because the nested ReAct loop legitimately takes minutes.
    - Image tools (``generate_image``, ``edit_image``): dedicated floor /
      ceiling pair (`image_generation_tool_timeout_seconds` /
      `max_image_generation_tool_timeout_seconds`) — a high-quality render
      measured 138.3 s, above the generic 120 s ceiling that used to apply.
    - Document tool (``generate_document``, ADR-226): dedicated floor /
      ceiling pair (`document_generation_tool_timeout_seconds` /
      `max_document_generation_tool_timeout_seconds`) — the internal LLM
      writes whole documents, well above the generic tool default.
    - ``claude_server_task_tool``: 120 s floor, `MAX_TOOL_TIMEOUT_SECONDS`
      ceiling.
    - MCP iterative task tools (``{server}_task``, ADR-062): dedicated
      floor / ceiling pair (`mcp_react_step_timeout_seconds` /
      `mcp_react_step_max_timeout_seconds`) — the nested ReAct loop
      legitimately runs several long LLM calls (audit D1).
    - Web-research tools (``unified_web_search_tool``, ``perplexity_*``):
      dedicated floor / ceiling pair (`web_research_tool_timeout_seconds` /
      `max_web_research_tool_timeout_seconds`) — the Perplexity-backed
      synthesis exceeds the generic 30 s (prod 2026-08).
    - Everything else: `DEFAULT_TOOL_TIMEOUT_SECONDS` (30 s) floor,
      `MAX_TOOL_TIMEOUT_SECONDS` (120 s) ceiling.

    For high-latency tools (image / sub-agent / devops / browser), the
    effective timeout is ``max(planner_request, family_default)`` capped by
    the family ceiling — this prevents the planner from imposing a too-short
    timeout that would kill the loop mid-task. For regular tools, it is just
    ``min(planner_request or default, ceiling)``.

    Args:
        step_tool_name: ``ExecutionStep.tool_name`` (``None`` falls back to
            the generic policy — happens for CONDITIONAL steps).
        step_requested_timeout: ``ExecutionStep.timeout_seconds`` as set by
            the planner (``None`` means "use the family default").

    Returns:
        Effective timeout in seconds. Always positive.
    """
    cfg = get_settings()
    # MCP iterative (ReAct) task steps (`{server}_task`, ADR-062): dedicated
    # high-latency family (audit D1). The generic 120 s ceiling used to clamp
    # the planner's request and killed legitimate multi-iteration work — one
    # diagram-generation LLM call alone takes ~105 s on a large model. The
    # explicit tool names above never end with the bare suffix
    # (`browser_task_tool`, `delegate_to_sub_agent_tool` end in `_tool`), so
    # there is no family overlap.
    is_mcp_react_task = bool(
        step_tool_name
        and step_tool_name.endswith(MCP_ITERATIVE_TASK_SUFFIX)
        and step_tool_name not in _HIGH_LATENCY_TOOL_NAMES
    )

    # Floor (effective default if planner left it unset, AND minimum for
    # high-latency tools — see docstring).
    if step_tool_name == _SUB_AGENT_TOOL_NAME:
        effective_default: float = cfg.subagent_tool_timeout_seconds
    elif step_tool_name in _IMAGE_TOOL_NAMES:
        effective_default = cfg.image_generation_tool_timeout_seconds
    elif step_tool_name in _DOCUMENT_TOOL_NAMES:
        effective_default = cfg.document_generation_tool_timeout_seconds
    elif step_tool_name == _DEVOPS_TOOL_NAME:
        effective_default = cfg.devops_claude_tool_timeout_seconds
    elif step_tool_name == _BROWSER_TOOL_NAME:
        effective_default = cfg.browser_tool_timeout_seconds
    elif step_tool_name in _WEB_RESEARCH_TOOL_NAMES:
        effective_default = cfg.web_research_tool_timeout_seconds
    elif is_mcp_react_task:
        effective_default = float(cfg.mcp_react_step_timeout_seconds)
    else:
        effective_default = cfg.default_tool_timeout_seconds

    # Ceiling.
    if step_tool_name == _BROWSER_TOOL_NAME:
        max_timeout: float = cfg.max_browser_tool_timeout_seconds
    elif step_tool_name == _SUB_AGENT_TOOL_NAME:
        max_timeout = cfg.subagent_tool_max_timeout_seconds
    elif step_tool_name in _IMAGE_TOOL_NAMES:
        # Dedicated ceiling: the generic 120 s sat BELOW the 138.3 s measured
        # for gpt-image-2 at quality=high, so raising the floor alone could
        # never make a high-quality render succeed (audit 2026-07-27).
        max_timeout = cfg.max_image_generation_tool_timeout_seconds
    elif step_tool_name in _DOCUMENT_TOOL_NAMES:
        # Dedicated ceiling (ADR-226): a large document at 16k output tokens
        # legitimately exceeds the generic 120 s cap.
        max_timeout = cfg.max_document_generation_tool_timeout_seconds
    elif step_tool_name in _WEB_RESEARCH_TOOL_NAMES:
        max_timeout = cfg.max_web_research_tool_timeout_seconds
    elif is_mcp_react_task:
        max_timeout = float(cfg.mcp_react_step_max_timeout_seconds)
    else:
        max_timeout = cfg.max_tool_timeout_seconds

    # High-latency tools: enforce family floor even if planner asked for less.
    if step_tool_name in _HIGH_LATENCY_TOOL_NAMES or is_mcp_react_task:
        return min(
            max(step_requested_timeout or effective_default, effective_default),
            max_timeout,
        )
    return min(step_requested_timeout or effective_default, max_timeout)
