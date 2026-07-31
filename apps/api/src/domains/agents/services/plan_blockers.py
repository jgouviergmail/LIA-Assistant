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
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Final

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


def summarize_plan_blockers(validation_result: object | None) -> list[PlanBlocker]:
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

    Returns:
        One blocker per distinct blocked tool, capped and order-preserved.
        Empty when the plan was valid, absent, or not a live verdict.
    """
    if not isinstance(validation_result, ValidationResult) or validation_result.is_valid:
        return []

    blockers: list[PlanBlocker] = []
    seen: set[str | None] = set()
    for issue in validation_result.errors:
        if issue.severity != "error" or issue.tool_name in seen:
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
