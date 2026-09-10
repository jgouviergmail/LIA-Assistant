"""Recording an ACTION performed outside the conversation graph.

The effect register is fed by one place — the tool gate — so a surface that
acts without calling a tool records nothing. That was true of the whole
proactive pipeline: a sweep decides on its own schedule to write to someone,
sends them a push notification, and left **no action row at all**. Measured
2026-09-07: ``agent_effects`` held rows from one authorship only (``user``),
and not a single ``proactive`` one had ever been written.

The consequence was reported from production the same day: a notification
arrived, and the « À l'initiative de LIA » tab showed nothing under « Actions
menées d'elle-même ». It was not a filter bug — there was nothing to filter.
And it was the sharpest possible gap, because a notification is the ONE act of
LIA's own initiative a person actually experiences.

The consultation register got its own out-of-turn recorder
(:func:`record_out_of_turn_consultation`); this is its counterpart for the
action register, and it keeps ADR-263's two-stage shape rather than writing a
finished row:

- **CLAIMED before the effect happens.** A push leaves the process; a claim
  written afterwards would be lost by the very crash it exists to survive.
- **SETTLED from an EXPLICIT result.** ``NotificationResult`` says whether any
  channel accepted it, so absence of an exception is never read as delivery.

Best-effort in full: the register must never cost the person their
notification.
"""

from __future__ import annotations

import uuid
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from dataclasses import dataclass

import structlog

logger = structlog.get_logger(__name__)

#: The capability name a proactive notification is recorded under. Bounded and
#: synthetic: no tool sends it, so nothing else would name it. Underscored
#: rather than colon-separated because it becomes an i18n key segment.
NOTIFICATION_CAPABILITY: str = "proactive_notification"

#: What the notification path claims. ``reversible`` is the honest policy: the
#: person can dismiss it and the archived message can be deleted, but it HAS
#: reached them — which is why it is not ``read`` and not ``artefact``.
NOTIFICATION_POLICY: str = "reversible"

#: Out of the graph, like every other out-of-turn row (ADR-270).
OUT_OF_TURN_EXECUTION_MODE: str = "direct"


@dataclass
class ProactiveEffect:
    """A claimed notification, waiting to be told how it went.

    Attributes:
        delivered: Set by the caller from the dispatch's explicit result.
            Left False, the row closes as a failure — the safe direction: an
            action that may not have reached anyone must not read as done.
    """

    delivered: bool = False


@asynccontextmanager
async def proactive_notification_effect(
    *,
    user_id: uuid.UUID,
    run_id: str,
    task_type: str,
    occurrence: str | None = None,
) -> AsyncIterator[ProactiveEffect]:
    """Claim the right to notify, then close the row from the dispatch result.

    Args:
        user_id: Who is being notified.
        run_id: The sweep this belongs to, shared with its consultations and
            its decision row so the three registers join.
        task_type: Which sweep decided to write — a bounded value
            (``heartbeat``, ``interest``…), never user text.
        occurrence: Which of the run's notifications this is, when a run
            speaks more than once — a workboard run says it started, then
            that it finished, or that it waits (ADR-276). None for a sweep
            that speaks once, whose key stays what it always was.

    Yields:
        The effect, whose ``delivered`` the caller sets from the dispatch.
    """
    effect = ProactiveEffect()
    ticket = await _claim(
        user_id=user_id, run_id=run_id, task_type=task_type, occurrence=occurrence
    )
    try:
        yield effect
    finally:
        if ticket is not None:
            await _close(ticket, delivered=effect.delivered)


def _idempotency_key(run_id: str, occurrence: str | None) -> str:
    """The identity of ONE notification within a run.

    A sweep that speaks once keeps the key it always had, so no row already
    written changes meaning; a run that speaks more than once names each
    thing it says.

    Args:
        run_id: The run.
        occurrence: What is being said, when the run says several things.

    Returns:
        The idempotency key.
    """
    base = f"{run_id}:notification"
    return base if occurrence is None else f"{base}:{occurrence}"


async def _claim(
    *, user_id: uuid.UUID, run_id: str, task_type: str, occurrence: str | None
) -> object | None:
    """Take the right to notify, in its own committed transaction.

    Args:
        user_id: Who is being notified.
        run_id: The sweep's correlation key.
        task_type: Which sweep decided to write.
        occurrence: Which of the run's notifications this is, or None.

    Returns:
        The claim ticket, or None when the ledger could not take it — the
        notification then goes out unrecorded rather than not at all.
    """
    try:
        from src.domains.agents.effects.digest import args_digest
        from src.domains.agents.effects.models import EffectSource
        from src.domains.agents.effects.runtime import _LEDGER
        from src.domains.agents.effects.schemas import ClaimRequest

        arguments = {"kind": task_type}
        return await _LEDGER.claim(
            ClaimRequest(
                user_id=user_id,
                thread_id=run_id,
                run_id=run_id,
                source=EffectSource.PROACTIVE.value,
                execution_mode=OUT_OF_TURN_EXECUTION_MODE,
                tool_name=NOTIFICATION_CAPABILITY,
                mutation_policy=NOTIFICATION_POLICY,
                # One claim per sweep AND per thing said: a retry of the same
                # run must not add a second « LIA notified you » to the
                # person's register — and the second thing a run says must
                # not be lost as a retry of the first. Measured 2026-09-09: a
                # followed ticket's « finished » was dispatched, and its row
                # was lost to the claim « started » had taken under the run.
                idempotency_key=_idempotency_key(run_id, occurrence),
                args_digest=args_digest(NOTIFICATION_CAPABILITY, arguments),
                label={
                    "i18n_key": f"effects.labels.{NOTIFICATION_CAPABILITY}",
                    "values": arguments,
                },
            )
        )
    except Exception as exc:  # noqa: BLE001 - the register never costs a notification
        logger.warning(
            "proactive_effect_not_claimed",
            task_type=task_type,
            error_type=type(exc).__name__,
        )
        return None


async def _close(ticket: object, *, delivered: bool) -> None:
    """Close the claimed row from what the dispatch actually reported.

    Args:
        ticket: The claim taken before the dispatch.
        delivered: Whether any channel accepted the notification.
    """
    try:
        from src.domains.agents.effects.outcome import ToolOutcome
        from src.domains.agents.effects.runtime import _LEDGER

        await _LEDGER.close(
            ticket.effect_id,  # type: ignore[attr-defined]
            ticket.claim_token,  # type: ignore[attr-defined]
            outcome=ToolOutcome(succeeded=delivered, provider_ref=None, payload=None),
        )
    except Exception as exc:  # noqa: BLE001 - the notification already went out
        logger.warning(
            "proactive_effect_not_closed",
            error_type=type(exc).__name__,
        )


__all__ = [
    "NOTIFICATION_CAPABILITY",
    "NOTIFICATION_POLICY",
    "ProactiveEffect",
    "proactive_notification_effect",
]
