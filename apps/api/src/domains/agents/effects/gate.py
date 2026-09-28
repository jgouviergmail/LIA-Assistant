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

from collections.abc import Iterable
from dataclasses import dataclass
from enum import Enum
from typing import Any, Final

from src.domains.agents.effects.scope import EffectScope

#: Policies whose effect happens somewhere the ledger cannot follow — or does
#: not happen at all at this point in the flow.
#:
#: - ``read`` changes nothing;
#: - ``sandboxed`` runs in a throwaway container with no host filesystem
#:   (SEC-001) and, by default, no network — so there is no external effect
#:   to record, and a ReAct loop calls it often enough that a row per run
#:   would be noise. A run that DOES reach the network (ADR-298) is the same
#:   tool under the same policy, invisible to this gate: the tool itself
#:   claims that act under ``python_sandbox_network``
#:   (``effects/in_turn_effects.py``), before the container starts;
#: - ``draft`` only BUILDS the confirmation the user will answer; the effect
#:   happens later, in the draft executor, which has its own gate. It is
#:   unconditional only where somebody can answer — see
#:   :data:`POLICIES_NEEDING_SOMEBODY`.
PASS_THROUGH_POLICIES: Final[frozenset[str]] = frozenset({"read", "sandboxed", "draft"})

#: Policies that cannot proceed when nobody is there to answer them.
#:
#: ``confirm`` was the original member: a pre-execution card nobody can click.
#: ``draft`` joined it (ADR-276) because it asks the same question by another
#: means — it RAISES a HITL interrupt — and measured on the routine path, that
#: interrupt becomes a non-retryable ``RuntimeError`` and STAYS on the thread,
#: so the person's next chat message is read as a decision they never made.
#:
#: A surface that can CARRY the question to the person is the exception (lot
#: 7): a workboard run captures the interrupt, puts the draft on the ticket
#: and clears the thread, so for it these two policies ask as they do in the
#: chat — see the ``carrier`` argument of :func:`decide_effect`.
POLICIES_NEEDING_SOMEBODY: Final[frozenset[str]] = frozenset({"confirm", "draft"})

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
# ADR-314 (amended 2026-09-27): the same refusal, naming the confirmation-free
# tool that declared itself this draft's stand-in (``stands_in_unattended_for``).
# Conditional on the tool being bound: the gate cannot see the turn's tool list,
# and the model can.
_MESSAGE_UNATTENDED_STAND_IN: Final[str] = (
    "This action requires an explicit confirmation and this turn runs "
    "unattended, so it cannot be obtained. Nothing was performed. If {when} "
    "and `{tool}` is among your tools, call it instead: it needs no "
    "confirmation. Otherwise, report that the action is waiting for the user, "
    "and never announce it as done."
)


def unattended_refusal_message(stand_in: str, when: str) -> str:
    """The unattended refusal that names the tool able to act in the draft's place.

    Args:
        stand_in: The confirmation-free tool that declared itself the stand-in.
        when: The case it covers, as its manifest states it.

    Returns:
        The technical English message the model reads.
    """
    return _MESSAGE_UNATTENDED_STAND_IN.format(when=when, tool=stand_in)


def assert_unattended_stand_ins(manifests: Iterable[Any]) -> None:
    """Refuse the boot on a stand-in declaration that cannot help (ADR-085).

    A stand-in is named in a refusal the loop acts on. Four ways to send it
    nowhere, each reported: naming a tool that does not exist; standing in for a
    tool that is never refused unattended (a dead declaration); needing a
    confirmation itself (the loop would be refused a second time, in the same
    turn); stating no case. And ONE stand-in per draft: the refusal names one.

    Args:
        manifests: Tool manifests currently registered in the catalogue.

    Raises:
        AssertionError: Listing every problem at once.
    """
    catalogue = {str(getattr(manifest, "name", "")): manifest for manifest in manifests}
    problems: list[str] = []
    claimed: dict[str, str] = {}
    for name, manifest in catalogue.items():
        stand_in = getattr(manifest, "stands_in_unattended_for", None)
        if stand_in is None:
            continue
        target = catalogue.get(stand_in.tool)
        if target is None:
            problems.append(f"{name}: stands in for unknown tool {stand_in.tool!r}")
        elif getattr(target, "mutation_policy", None) not in POLICIES_NEEDING_SOMEBODY:
            problems.append(f"{name}: {stand_in.tool} is never refused unattended")
        if getattr(manifest, "mutation_policy", None) in POLICIES_NEEDING_SOMEBODY:
            problems.append(f"{name}: needs a confirmation itself")
        if not str(stand_in.when).strip():
            problems.append(f"{name}: states no case")
        if stand_in.tool in claimed:
            problems.append(f"{stand_in.tool}: two stand-ins ({claimed[stand_in.tool]}, {name})")
        claimed.setdefault(stand_in.tool, name)
    if problems:
        raise AssertionError(
            f"{len(problems)} unattended stand-in problem(s): " + "; ".join(sorted(problems))
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


def decide_effect(
    policy: str | None, scope: EffectScope | None, *, carrier: bool = False
) -> GateDecision:
    """Decide what happens to one tool call.

    Args:
        policy: The tool's declared ``mutation_policy``; None for a registered
            instance with no manifest (22 of them: the browser sub-tools the
            browser loop calls, and the legacy readers no planner can reach).
        scope: The authority the executor published, or None when none did.
        carrier: True when the turn is driven by a surface that can put a
            draft in front of the person and wait for their answer — a
            workboard ticket (ADR-276, lot 7). Nobody is there NOW, but the
            question has somewhere to go: a ``confirm`` becomes the draft the
            chat would have shown and a ``draft`` builds its own, and the run
            captures the interrupt instead of leaving it on the thread.

    Returns:
        The verdict. Pure: no I/O, no clock, no registry — every branch is
        enumerable in a unit test.
    """
    unattended = scope is not None and scope.source in UNATTENDED_SOURCES and not carrier

    # A DRAFT is only ever a pass-through where somebody can answer it. Nobody
    # can, here — so it is refused rather than raising an interrupt that would
    # outlive the run (ADR-276 amends ADR-263).
    if (
        policy in POLICIES_NEEDING_SOMEBODY
        and unattended
        and not (scope is not None and scope.approved)
    ):
        return GateDecision(
            action=GateAction.REFUSE,
            error_code=ERROR_CONFIRMATION_IMPOSSIBLE,
            llm_message=_MESSAGE_UNATTENDED,
        )

    if policy is None or policy in PASS_THROUGH_POLICIES:
        return GateDecision(action=GateAction.PASS_THROUGH)

    if policy == "confirm" and not (scope is not None and scope.approved):
        return GateDecision(
            action=GateAction.REFUSE,
            error_code=ERROR_CONFIRMATION_MISSING,
            llm_message=_MESSAGE_MISSING,
        )

    return GateDecision(action=GateAction.LEDGER, unscoped=scope is None)
