"""Turning a refused plan into something the response can honestly say.

The validator already knows precisely why a plan cannot run — which step, which
tool, which ``ToolErrorCode``. That verdict was logged and then dropped: the
turn continued, the tools returned empty, and the response LLM was left to
explain a silence it had no information about. It did what models do with a
silence: it filled it with a plausible story.

Measured on 2026-07-30 (requests 303d7ce3, 43e9bded), three consecutive turns:
the validator rejected ``get_events_tool`` and ``get_contacts_tool`` for
missing OAuth scopes, and the assistant told the user "aucun service de
contacts ni d'agenda n'est configuré", then "je n'ai toujours pas d'yeux pour
lire dans vos agendas", then "tu espères un miracle technologique sans vouloir
faire le moindre effort de configuration". Every sentence was false: the peer
whose calendar was asked about had a healthy connector, and the real fault was
a routing mistake upstream. A confidently wrong diagnosis is worse than an
admission of failure — the user acts on it.

Scope note: this is deliberately NOT specific to OAuth scopes. The failure mode
belongs to the silence, not to the error code, so every ``ToolErrorCode`` the
validator can emit produces the same honest report — including codes with no
explicit mapping, which degrade to "blocked, cause unnamed" rather than to
nothing.

Second measurement, 2026-07-31 (request 83c98053), which added the execution
filter below: the validator rejected ``max_results=20`` against a cap of 10,
the step ran anyway, ten emails reached the registry — and the answer told the
user the retrieval "had been blocked by a limit" and sent them to check their
email connector. The verdict was stale by the time it was read.

The verdict alone cannot mean "blocked", because nothing acts on it: the router
never reads ``is_valid`` and executes rejected plans unchanged. So a blocker is
only real for a capability that never ran — which is exactly what the founding
defect looked like, and exactly what this one did not.

Third measurement, 2026-10-07 (run b148e908, RC1.2): a step that RAN and
FAILED kept its verdict. An Outlook account's reply failed on its own
reference, the validator had judged it ``UNAUTHORIZED`` against Google scopes,
and the « blocked » directive — marked authoritative — told the person the
reply capability was « not connected », while the runtime failures directive,
which carried the real failure, forbade saying exactly that. A capability that
ran answers through ONE channel, its own typed failure (ADR-303); a verdict
speaks only for what never ran.
"""

from __future__ import annotations

from collections.abc import Collection
from dataclasses import dataclass
from typing import Final

from src.domains.agents.orchestration.plan_schemas import (
    FOR_EACH_ITEM_INFIX,
    ExecutionPlan,
    StepType,
)
from src.domains.agents.orchestration.validator import ValidationResult
from src.domains.agents.tools.common import ToolErrorCode

# Cause phrasings handed to the response LLM. English, like every other
# prompt fragment: the directive orders the answer in the user's language, and
# the model translates the cause with the rest. Deliberately capability-level
# ("has not been authorized") rather than mechanism-level ("missing scope
# https://www.googleapis.com/auth/calendar"): the raw value is token waste, it
# means nothing to the user, and the model tends to quote what it is shown.
BLOCKER_REASONS: Final[dict[ToolErrorCode, str]] = {
    ToolErrorCode.UNAUTHORIZED: (
        "the user has not connected or authorized this capability for their own account"
    ),
    ToolErrorCode.FORBIDDEN: "this account is not allowed to use this capability",
    ToolErrorCode.CONFIGURATION_ERROR: "this capability is not configured on this deployment",
    ToolErrorCode.NOT_IMPLEMENTED: "this capability does not exist yet",
    ToolErrorCode.NOT_FOUND: "the requested item or capability could not be found",
    ToolErrorCode.MISSING_REQUIRED_PARAM: "a required detail was missing from the request",
    ToolErrorCode.INVALID_PARAM_VALUE: "a detail of the request was not usable as given",
    ToolErrorCode.INVALID_INPUT: "the request could not be turned into a runnable step",
    ToolErrorCode.CONSTRAINT_VIOLATION: "the request broke a limit enforced on this capability",
    ToolErrorCode.RATE_LIMIT_EXCEEDED: "this capability was called too often and is rate-limited",
    ToolErrorCode.DEPENDENCY_ERROR: "it depended on an earlier step that could not run",
}

# Fallback for any code without an explicit phrasing. The honesty layer must
# degrade to a vaguer truth, never to silence — silence is the defect.
UNMAPPED_BLOCKER_REASON: Final[str] = "it could not be validated as runnable"

# A plan with dozens of rejected steps says one thing ("nothing ran"); listing
# them all would only crowd the response prompt.
_MAX_BLOCKERS: Final[int] = 10


@dataclass(frozen=True)
class PlanBlocker:
    """One capability the validator refused to let the plan use.

    Attributes:
        tool_name: The blocked tool, or None for a plan-level rejection.
        code: ``ToolErrorCode`` value, kept for logs and metrics.
        reason: Capability-level cause, phrased for the response LLM.
    """

    tool_name: str | None
    code: str
    reason: str


def attempted_tool_names(
    execution_plan: object | None,
    completed_steps: object | None,
) -> frozenset[str]:
    """Names of the tools the turn actually tried, whatever they answered.

    A step counts as soon as the orchestrator stored an outcome for it — under
    its own id, or under one of its FOR_EACH items (``step_2_item_0``). Zero
    items is an answer, and so is a failure: its typed failure reaches the
    runtime failures directive, which is that fact's one channel (RC1.2).

    Args:
        execution_plan: ``ExecutionPlan`` from state — it holds the only
            step_id → tool_name mapping (``completed_steps`` is keyed by
            step_id alone). FOR_EACH expansions are aggregated back under the
            original step_id by the executor, so this mapping stays complete.
        completed_steps: ``{step_id: result}`` written by the task
            orchestrator.

    Returns:
        The attempted tool names, empty whenever either input is absent or came
        back from a msgpack round-trip in an unexpected shape. Empty is the
        safe default: it restores the pre-existing behaviour of reporting every
        blocker, never the reverse.
    """
    if not isinstance(execution_plan, ExecutionPlan) or not isinstance(completed_steps, dict):
        return frozenset()

    stored = {str(key) for key in completed_steps}
    attempted: set[str] = set()
    for step in execution_plan.steps:
        if step.step_type != StepType.TOOL or not step.tool_name:
            continue
        item_prefix = f"{step.step_id}{FOR_EACH_ITEM_INFIX}"
        if step.step_id in stored or any(key.startswith(item_prefix) for key in stored):
            attempted.add(step.tool_name)
    return frozenset(attempted)


def summarize_plan_blockers(
    validation_result: object | None,
    attempted_tools: Collection[str] = (),
) -> list[PlanBlocker]:
    """Reduce a validation verdict to the capabilities that were blocked.

    Args:
        validation_result: ``ValidationResult`` from the plan validator, or
            None on turns that never ran it (conversation, ReAct). Typed
            ``object`` on purpose: this reads a LangGraph state key, and state
            survives msgpack round-trips — after a HITL resume the value may
            come back as a plain mapping rather than the dataclass. The
            isinstance check below is what makes that harmless (and narrows the
            type for everything after it) instead of raising inside the
            response node, where an exception costs the whole answer.
        attempted_tools: Tools that ran despite the verdict, from
            :func:`attempted_tool_names`. A rejected plan is executed
            unchanged — the router never reads ``is_valid`` — so a capability
            that ran was demonstrably not blocked, whatever the verdict says
            about it, and whatever it answered. Defaults to empty, which keeps
            every blocker for callers that have no execution knowledge.

    Returns:
        One blocker per distinct blocked tool, capped and order-preserved.
        Empty when the plan was valid, absent, not a live verdict, or when
        every rejected capability ended up running.
    """
    if not isinstance(validation_result, ValidationResult) or validation_result.is_valid:
        return []

    attempted = frozenset(attempted_tools)
    blockers: list[PlanBlocker] = []
    seen: set[str | None] = set()
    for issue in validation_result.errors:
        if issue.severity != "error" or issue.tool_name in seen:
            continue
        # The capability ran: reporting it as blocked is the defect, not the
        # fix — its own outcome, data or typed failure, is what the answer
        # reads. A plan-level rejection (no tool named) is silenced as soon as
        # anything ran at all — "the plan itself was blocked" cannot be true
        # of a plan that executed.
        if issue.tool_name in attempted or (issue.tool_name is None and attempted):
            continue
        seen.add(issue.tool_name)
        blockers.append(
            PlanBlocker(
                tool_name=issue.tool_name,
                code=issue.code.value,
                reason=BLOCKER_REASONS.get(issue.code, UNMAPPED_BLOCKER_REASON),
            )
        )
        if len(blockers) >= _MAX_BLOCKERS:
            break
    return blockers


def format_plan_blockers(blockers: list[PlanBlocker]) -> str:
    """Render blockers as the fact list injected in the response directive.

    Args:
        blockers: Output of :func:`summarize_plan_blockers`.

    Returns:
        One ``- tool: reason`` line per blocker, or ``""`` when there is
        nothing to report (an empty system block is rejected by Anthropic, so
        the caller must skip the directive entirely on an empty string).
    """
    if not blockers:
        return ""
    return "\n".join(
        f"- {blocker.tool_name or 'the plan itself'}: {blocker.reason}" for blocker in blockers
    )
