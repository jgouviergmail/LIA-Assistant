"""The one place an effect is allowed to happen (ADR-263).

The gate is installed on the TOOL, at registration, not on its callers. That is
the whole point: measured 2026-09-03, the same capability is reached three
different ways — ``tool.coroutine(**args)`` from the pipeline executor, the same
call from the ReAct loop, and ``tool.ainvoke(...)`` from the sub-agent runner —
and a fourth caller is one refactor away. A gate its callers must remember to
call is a gate that will be forgotten; a gate on the capability itself cannot be
walked around.

The decision is a pure function (:func:`decide_effect`) so every branch can be
enumerated in a unit test, and the I/O around it (claim, run, close) is the only
part that needs a database.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Final

from src.domains.agents.effects.scope import EffectScope

#: Policies whose effect happens somewhere the ledger cannot follow — or does
#: not happen at all at this point in the flow.
#:
#: - ``read`` changes nothing;
#: - ``sandboxed`` runs in a throwaway container with no network and no host
#:   filesystem (SEC-001), so there is no external effect to record — and a
#:   ReAct loop calls it often enough that a row per run would be noise;
#: - ``draft`` only BUILDS the confirmation the user will answer; the effect
#:   happens later, in the draft executor, which has its own gate.
PASS_THROUGH_POLICIES: Final[frozenset[str]] = frozenset({"read", "sandboxed", "draft"})

#: Policies that reach the world and are therefore recorded.
LEDGERED_POLICIES: Final[frozenset[str]] = frozenset({"reversible", "artefact", "confirm"})

#: Sources that have nobody to ask. A ``confirm`` effect is not "unconfirmed"
#: there — it is unconfirmable, and saying so is the difference between an
#: honest report and an invented diagnosis (ADR-182).
UNATTENDED_SOURCES: Final[frozenset[str]] = frozenset({"scheduled"})

ERROR_CONFIRMATION_MISSING: Final[str] = "confirmation_missing"
ERROR_CONFIRMATION_IMPOSSIBLE: Final[str] = "confirmation_impossible_unattended"

# Technical English for the model, which reformulates in the user's language —
# the doctrine every tool-facing message in this codebase follows (ADR-256).
_MESSAGE_MISSING: Final[str] = (
    "This action requires an explicit confirmation from the user and none was "
    "recorded for this call. Present what you intend to do and ask for it."
)
_MESSAGE_UNATTENDED: Final[str] = (
    "This action requires an explicit confirmation and this turn runs "
    "unattended, so it cannot be obtained. Nothing was performed. Report that "
    "the action is waiting for the user, and never announce it as done."
)


class GateAction(str, Enum):
    """What the gate does with a call."""

    PASS_THROUGH = "pass_through"
    """Run it, record nothing: it reaches nothing the ledger tracks."""

    LEDGER = "ledger"
    """Claim before, run, close from the result."""

    REFUSE = "refuse"
    """Do not run it: the authority is missing."""


@dataclass(frozen=True)
class GateDecision:
    """The verdict on one call.

    Attributes:
        action: What to do.
        error_code: Stable code of a refusal, else None.
        llm_message: What the model is told on a refusal, in technical English.
        unscoped: True when the call is ledgered without an executor scope — it
            still runs, and it is counted, because a silence here is how a
            fourth caller would appear unnoticed.
    """

    action: GateAction
    error_code: str | None = None
    llm_message: str | None = None
    unscoped: bool = False


def decide_effect(policy: str | None, scope: EffectScope | None) -> GateDecision:
    """Decide what happens to one tool call.

    Args:
        policy: The tool's declared ``mutation_policy``; None for a registered
            instance with no manifest (22 of them: the browser sub-tools the
            browser loop calls, and the legacy readers no planner can reach).
        scope: The authority the executor published, or None when none did.

    Returns:
        The verdict. Pure: no I/O, no clock, no registry — every branch is
        enumerable in a unit test.
    """
    if policy is None or policy in PASS_THROUGH_POLICIES:
        return GateDecision(action=GateAction.PASS_THROUGH)

    if policy == "confirm" and not (scope is not None and scope.approved):
        unattended = scope is not None and scope.source in UNATTENDED_SOURCES
        return GateDecision(
            action=GateAction.REFUSE,
            error_code=(
                ERROR_CONFIRMATION_IMPOSSIBLE if unattended else ERROR_CONFIRMATION_MISSING
            ),
            llm_message=_MESSAGE_UNATTENDED if unattended else _MESSAGE_MISSING,
        )

    return GateDecision(action=GateAction.LEDGER, unscoped=scope is None)
