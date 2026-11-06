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
  LLM writes whole documents, well above 30 s); a page shares them (ADR-370)
- web rsrch : ``web_research_tool_timeout_seconds`` /
  ``max_web_research_tool_timeout_seconds`` (Perplexity-backed synthesis,
  killed at the generic 30 s in prod 2026-08)
- devops    : ``devops_claude_tool_timeout_seconds``, generic ceiling

The image family got its own ceiling on 2026-07-27: a measured 138.3 s
render sat above the generic 120 s cap, so no floor value could have
rescued it.

Those numbers are the environment's, and it has no word over the database: a
tool declared in :data:`TOOL_LLM_SLOTS` waits for the calls it makes, whatever
its family says (ADR-221 amendment 2026-11-05). ReAct asks for no timeout, so a
family's floor is all a call ever gets there.
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import TYPE_CHECKING

from src.core.config import get_settings
from src.core.constants import MCP_ITERATIVE_TASK_SUFFIX, MCP_TOOL_NAME_PREFIX
from src.core.llm_config_helper import run_bound_seconds

if TYPE_CHECKING:
    from src.core.config import Settings

# Tool-name groupings consumed by `compute_step_timeout`. Kept at module
# scope (not inside the helper) so the timeout policy is greppable and the
# constants are evaluated once, not on every step.
_BROWSER_TOOL_NAME = "browser_task_tool"
_DEVOPS_TOOL_NAME = "claude_server_task_tool"
_SUB_AGENT_TOOL_NAME = "delegate_to_sub_agent_tool"
#: A third-party skill's activation RUNS it, in the isolated skill runner
#: (ADR-327): a nested loop like a delegation, killed at the generic 30 s
#: three times in one dev session (2026-09-30) — the sub-agent family's bounds.
_SKILL_ACTIVATION_TOOL_NAME = "activate_skill_tool"
_NESTED_LOOP_TOOL_NAMES: frozenset[str] = frozenset(
    {_SUB_AGENT_TOOL_NAME, _SKILL_ACTIVATION_TOOL_NAME}
)
_IMAGE_TOOL_NAMES: frozenset[str] = frozenset({"generate_image", "edit_image"})
_DOCUMENT_TOOL_NAMES: frozenset[str] = frozenset({"generate_document", "generate_interactive_page"})
#: A skill's script and command (ADR-327 lot 2): the sandbox bounds them itself,
#: so the step waits exactly that bound — floor AND ceiling, never the generic
#: 30 s that cut a command the sandbox still allowed.
_SKILL_SCRIPT_TOOL_NAME = "run_skill_script"
_SKILL_COMMAND_TOOL_NAME = "run_skill_command"
# Web research backed by an external LLM (Perplexity synthesis / unified
# multi-source search): prod 2026-08-14→20 measured these killed at the
# generic 30 s while the synthesis legitimately runs longer.
_WEB_RESEARCH_TOOL_NAMES: frozenset[str] = frozenset(
    {"unified_web_search_tool", "perplexity_search_tool", "perplexity_ask_tool"}
)
#: What a tool asks of the model, in the order it asks. Its step waits for these
#: calls whatever its family says (ADR-221 amendment 2026-11-05); the guard
#: ``test_llm_wall_clock_guard.py`` refuses a tool module reaching a model unlisted.
TOOL_LLM_SLOTS: Mapping[str, tuple[str, ...]] = {
    _SUB_AGENT_TOOL_NAME: ("subagent",),
    _SKILL_ACTIVATION_TOOL_NAME: ("mcp_react_agent",),
    _BROWSER_TOOL_NAME: ("browser_agent",),
    "generate_image": ("image_prompt_enhancement", "image_generation"),
    "edit_image": ("image_generation",),
    "generate_document": ("document_generation",),
    "generate_interactive_page": ("interactive_page",),
    "get_emails_tool": ("email_digest",),
    "get_email_attachment_tool": ("vision_analysis",),
    "send_email_tool": ("emails_agent",),
    "send_email_to_me_tool": ("emails_agent",),
    "create_mailbox_draft_tool": ("emails_agent",),
    "create_mailbox_reply_draft_tool": ("emails_agent",),
    "update_mailbox_draft_tool": ("hitl_question_generator",),
}
#: A server's task runs on ONE of these, chosen from what the server exposes.
_MCP_TASK_LLM_SLOTS: tuple[str, ...] = ("mcp_react_agent", "mcp_app_react_agent")
_HIGH_LATENCY_TOOL_NAMES: frozenset[str] = (
    _IMAGE_TOOL_NAMES
    | _DOCUMENT_TOOL_NAMES
    | _WEB_RESEARCH_TOOL_NAMES
    | _NESTED_LOOP_TOOL_NAMES
    | frozenset({_DEVOPS_TOOL_NAME, _BROWSER_TOOL_NAME})
    | frozenset(TOOL_LLM_SLOTS)
)


def _family_floor(
    cfg: Settings, step_tool_name: str | None, *, is_mcp_react_task: bool, is_direct_mcp_call: bool
) -> float:
    """The floor of a tool's family: its default, and its minimum when high-latency.

    Args:
        cfg: The settings.
        step_tool_name: The tool, ``None`` for a CONDITIONAL step.
        is_mcp_react_task: The tool is an iterative MCP task.
        is_direct_mcp_call: The tool is a direct MCP call.

    Returns:
        The floor, in seconds.
    """
    if step_tool_name in _NESTED_LOOP_TOOL_NAMES:
        return cfg.subagent_tool_timeout_seconds
    if step_tool_name in _IMAGE_TOOL_NAMES:
        return cfg.image_generation_tool_timeout_seconds
    if step_tool_name in _DOCUMENT_TOOL_NAMES:
        return cfg.document_generation_tool_timeout_seconds
    if step_tool_name == _DEVOPS_TOOL_NAME:
        return cfg.devops_claude_tool_timeout_seconds
    if step_tool_name == _BROWSER_TOOL_NAME:
        return cfg.browser_tool_timeout_seconds
    if step_tool_name in _WEB_RESEARCH_TOOL_NAMES:
        return cfg.web_research_tool_timeout_seconds
    if is_mcp_react_task:
        return float(cfg.mcp_react_step_timeout_seconds)
    if is_direct_mcp_call:
        return float(cfg.mcp_tool_timeout_seconds)
    return cfg.default_tool_timeout_seconds


def _family_ceiling(
    cfg: Settings, step_tool_name: str | None, *, is_mcp_react_task: bool, is_direct_mcp_call: bool
) -> float:
    """The most a tool's family grants a step.

    Args:
        cfg: The settings.
        step_tool_name: The tool, ``None`` for a CONDITIONAL step.
        is_mcp_react_task: The tool is an iterative MCP task.
        is_direct_mcp_call: The tool is a direct MCP call.

    Returns:
        The ceiling, in seconds.
    """
    if step_tool_name == _BROWSER_TOOL_NAME:
        return cfg.max_browser_tool_timeout_seconds
    if step_tool_name in _NESTED_LOOP_TOOL_NAMES:
        return cfg.subagent_tool_max_timeout_seconds
    if step_tool_name in _IMAGE_TOOL_NAMES:
        # Dedicated ceiling: the generic 120 s sat BELOW the 138.3 s measured
        # for gpt-image-2 at quality=high, so raising the floor alone could
        # never make a high-quality render succeed (audit 2026-07-27).
        return cfg.max_image_generation_tool_timeout_seconds
    if step_tool_name in _DOCUMENT_TOOL_NAMES:
        # Dedicated ceiling (ADR-226): a large document at 16k output tokens
        # legitimately exceeds the generic 120 s cap.
        return cfg.max_document_generation_tool_timeout_seconds
    if step_tool_name in _WEB_RESEARCH_TOOL_NAMES:
        return cfg.max_web_research_tool_timeout_seconds
    if is_mcp_react_task:
        return float(cfg.mcp_react_step_max_timeout_seconds)
    if is_direct_mcp_call:
        return float(cfg.mcp_tool_timeout_seconds)
    return cfg.max_tool_timeout_seconds


def _floor_under_the_slots(
    floor: float, step_tool_name: str | None, *, is_mcp_react_task: bool
) -> float:
    """A family's floor, lifted to what the tool's model calls may take.

    Args:
        floor: The family's floor.
        step_tool_name: The tool, ``None`` for a CONDITIONAL step.
        is_mcp_react_task: The tool is an iterative MCP task.

    Returns:
        The floor, in seconds: the family's, unless a slot needs longer.
    """
    if is_mcp_react_task:
        return max(run_bound_seconds(floor, slot) for slot in _MCP_TASK_LLM_SLOTS)
    return run_bound_seconds(floor, *TOOL_LLM_SLOTS.get(step_tool_name or "", ()))


def compute_step_timeout(
    step_tool_name: str | None,
    step_requested_timeout: float | None,
) -> float:
    """Compute the effective timeout (seconds) for an ExecutionStep.

    Implements the per-tool-family policy:

    - ``delegate_to_sub_agent_tool`` and ``activate_skill_tool`` (which runs a
      third-party skill in its isolated runner, ADR-327): floor / ceiling
      tunable via Settings (`subagent_tool_timeout_seconds` /
      `subagent_tool_max_timeout_seconds`), so operators can adjust without
      touching application-wide constants.
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
    - Page tool (``generate_interactive_page``, ADR-370): the document family.
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
    - Direct MCP calls (``mcp_*`` that are not a ``{server}_task`` tool,
      ADR-256): `mcp_tool_timeout_seconds` as BOTH floor and ceiling. The MCP
      layer already wraps every call in a wait_for of its own — that setting
      for admin servers, and for a user server the `timeout_seconds` its owner
      chose (5..120) — so the generic 30 s floor would have made this the
      strictest voice in the chain and cut a call the layer below still
      accepted. An explicit `step_requested_timeout` remains an intention and
      is still honoured, exactly as it is for every non-high-latency family.
    - A skill's script or command (``run_skill_script``,
      ``run_skill_command``, ADR-327 lot 2): the sandbox's own wall budget as
      BOTH floor and ceiling — the container bounds the run, and the generic
      30 s would cut a command the sandbox still allows.
    - Everything else: `DEFAULT_TOOL_TIMEOUT_SECONDS` (30 s) floor,
      `MAX_TOOL_TIMEOUT_SECONDS` (120 s) ceiling.

    For high-latency tools (image / sub-agent / devops / browser, and every
    tool of :data:`TOOL_LLM_SLOTS`), the effective timeout is
    ``max(planner_request, family_default)`` capped by the family ceiling — this
    prevents the planner from imposing a too-short timeout that would kill the
    loop mid-task. For regular tools, it is just
    ``min(planner_request or default, ceiling)``.

    Above all of it stand the slots a tool calls (ADR-221 amendment 2026-11-05):
    the floor rises to what those calls may take, the ceiling with it.

    Args:
        step_tool_name: ``ExecutionStep.tool_name`` (``None`` falls back to
            the generic policy — happens for CONDITIONAL steps).
        step_requested_timeout: ``ExecutionStep.timeout_seconds`` as set by
            the planner (``None`` means "use the family default").

    Returns:
        Effective timeout in seconds. Always positive.
    """
    cfg = get_settings()
    if step_tool_name == _SKILL_COMMAND_TOOL_NAME:
        return float(cfg.skill_command_wall_seconds)
    if step_tool_name == _SKILL_SCRIPT_TOOL_NAME:
        return float(cfg.skills_script_wall_seconds)
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

    # A DIRECT MCP call (ADR-256). The MCP layer already wraps every call in an
    # asyncio.wait_for of its own — `mcp_tool_timeout_seconds` for admin
    # servers, and for a user server the `timeout_seconds` its owner set
    # (5..120). Leaving these tools on the generic 30 s floor would put a
    # SECOND, stricter authority above a setting the user chose, and would cut
    # a call the layer below was still willing to make. Ours therefore matches
    # the MCP bound: the loop stops being unbounded without ever becoming the
    # strictest voice in the chain.
    is_direct_mcp_call = bool(
        step_tool_name
        and step_tool_name.startswith(f"{MCP_TOOL_NAME_PREFIX}_")
        and not is_mcp_react_task
        and step_tool_name not in _HIGH_LATENCY_TOOL_NAMES
    )

    # Floor (effective default if planner left it unset, AND minimum for
    # high-latency tools — see docstring), lifted to the tool's model calls.
    effective_default = _floor_under_the_slots(
        _family_floor(
            cfg,
            step_tool_name,
            is_mcp_react_task=is_mcp_react_task,
            is_direct_mcp_call=is_direct_mcp_call,
        ),
        step_tool_name,
        is_mcp_react_task=is_mcp_react_task,
    )
    max_timeout = max(
        effective_default,
        _family_ceiling(
            cfg,
            step_tool_name,
            is_mcp_react_task=is_mcp_react_task,
            is_direct_mcp_call=is_direct_mcp_call,
        ),
    )

    # High-latency tools: enforce family floor even if planner asked for less.
    if step_tool_name in _HIGH_LATENCY_TOOL_NAMES or is_mcp_react_task:
        return min(
            max(step_requested_timeout or effective_default, effective_default),
            max_timeout,
        )
    return min(step_requested_timeout or effective_default, max_timeout)
