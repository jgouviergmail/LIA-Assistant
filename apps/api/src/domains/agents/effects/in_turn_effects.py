"""Recording an ACTION a tool performs inside the turn, beside its own gate.

The gate claims an effect for a tool whose POLICY is ledgered. The sandbox
tool is ``sandboxed`` — pass-through, because an air-gapped run has no
external effect to record. A NETWORK run (ADR-298) does: a script reached
hosts, possibly with the person's data and the person's own key. It is the
same tool, so the gate cannot tell the two apart; the tool itself claims the
network act here, under a capability name of its own, before the container
starts, and closes it from the result.

Same two-stage shape as the proactive notification's
(:mod:`out_of_turn_effects`), built from the RUNNING context rather than a
sweep's identifiers, so the row lands under the turn the other registers
already share.
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from dataclasses import dataclass
from typing import Any

import structlog

logger = structlog.get_logger(__name__)

#: The capability a network sandbox run is recorded under. Synthetic and
#: bounded, like ``proactive_notification``: no catalogue tool carries it.
SANDBOX_NETWORK_CAPABILITY: str = "python_sandbox_network"


@dataclass
class InTurnEffect:
    """A claimed act, waiting to be told how it went.

    Attributes:
        succeeded: Set by the caller from the run's explicit result. Left
            False, the row closes as a failure — a run that raised before
            reporting must not read as done.
    """

    succeeded: bool = False


@asynccontextmanager
async def in_turn_effect(
    *, tool_name: str, policy: str, arguments: dict[str, Any]
) -> AsyncIterator[InTurnEffect]:
    """Claim the act, yield, close from the result.

    Args:
        tool_name: The capability recorded (``SANDBOX_NETWORK_CAPABILITY``).
        policy: The mutation policy the row carries.
        arguments: What the act was asked (digested, and read by the label).

    Yields:
        The effect, whose ``succeeded`` the caller sets.
    """
    effect = InTurnEffect()
    ticket = await _claim(tool_name=tool_name, policy=policy, arguments=arguments)
    try:
        yield effect
    finally:
        if ticket is not None and ticket.claim_token is not None:
            await _close(ticket, succeeded=effect.succeeded)


async def _claim(*, tool_name: str, policy: str, arguments: dict[str, Any]) -> Any:
    """Take the row in its own transaction; None when nobody owns it or the
    ledger is down — the run then happens unrecorded rather than not at all."""
    from src.domains.agents.effects.runtime import _LEDGER, claim_request_for

    try:
        request = claim_request_for(tool_name, policy, arguments)
        if request is None:
            return None
        return await _LEDGER.claim(request)
    except Exception as exc:  # noqa: BLE001 - the register never costs the run
        logger.warning(
            "in_turn_effect_not_claimed", tool_name=tool_name, error_type=type(exc).__name__
        )
        return None


async def _close(ticket: Any, *, succeeded: bool) -> None:
    """Close the claimed row from what the run actually reported."""
    from src.domains.agents.effects.outcome import ToolOutcome
    from src.domains.agents.effects.runtime import _LEDGER

    try:
        await _LEDGER.close(
            ticket.effect_id,
            ticket.claim_token,
            outcome=ToolOutcome(succeeded=succeeded, provider_ref=None, payload=None),
        )
    except Exception as exc:  # noqa: BLE001 - the act already happened
        logger.warning("in_turn_effect_not_closed", error_type=type(exc).__name__)


__all__ = ["SANDBOX_NETWORK_CAPABILITY", "InTurnEffect", "in_turn_effect"]
