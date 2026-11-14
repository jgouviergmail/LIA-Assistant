"""What a tick of a routine started by calls serves, and when it rests (ADR-386).

The executor's third gate, beside the condition's. A webhook routine's tick
runs only on calls that wait for it:

- **what it serves**: its oldest waiting calls, at most
  ``routine_webhook_max_per_run``, shown to the run after the routine's own
  instruction (``webhooks.calls_note``) — while the capability is open: a
  closed switch stops the ACT, the calls already accepted stay recorded;
- **when it rests**: with nothing to serve, the routine sleeps until a call
  wakes it. Decided under the routine's lock, where a call that slipped in
  between the read and the settle is seen and re-arms it at once — the call's
  own arming was just overwritten by this settle. Closed, a routine whose calls
  wait looks again after the failure back-off, so a switch that reopens finds
  them served without a new call. The switch is the one the tick read at its
  start: nothing is asked of a store while the row is held (ADR-304);
- **what it marks**: the calls a run that ANSWERED read, served in the
  transaction of the routine's own settle (and counted).
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from datetime import datetime, timedelta
from uuid import UUID

import structlog
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.config import settings
from src.core.constants import ROUTINE_WEBHOOK_FAILURE_RETRY_SECONDS
from src.core.time_utils import now_utc
from src.domains.feature_switches.registry import PlatformCapability, is_capability_enabled
from src.domains.scheduled_actions.models import ScheduledAction
from src.domains.scheduled_actions.webhook_repository import RoutineWebhookRepository
from src.domains.scheduled_actions.webhooks import calls_note
from src.infrastructure.observability.metrics_routine_webhooks import (
    routine_webhook_calls_served_total,
)

logger = structlog.get_logger(__name__)


@dataclass(frozen=True, slots=True)
class WaitingCalls:
    """What one tick of a webhook routine found: the switch, and the calls it serves."""

    switch_open: bool
    """The operator's switch, read at the tick's start — before any lock (ADR-304)."""
    note: str = ""
    """What the run is shown of the calls, after the routine's instruction."""
    delivery_ids: tuple[UUID, ...] = ()
    """Their rows, marked served if the run answers; empty when nothing is served."""


async def waiting_calls(db: AsyncSession, action: ScheduledAction) -> WaitingCalls:
    """The switch, then the calls this tick serves.

    Args:
        db: The tick's session (the read is the caller's to end).
        action: The webhook routine.

    Returns:
        The calls and their note; none when none waits, or when the capability
        is closed (logged) — the tick then rests.
    """
    if not await is_capability_enabled(PlatformCapability.ROUTINE_WEBHOOKS):
        logger.info("routine_webhook_tick_capability_closed", action_id=str(action.id))
        return WaitingCalls(switch_open=False)
    calls = await RoutineWebhookRepository(db).pending(
        action.id, limit=settings.routine_webhook_max_per_run
    )
    if not calls:
        return WaitingCalls(switch_open=True)
    return WaitingCalls(
        switch_open=True,
        note=calls_note(calls, timezone=action.user_timezone),
        delivery_ids=tuple(call.id for call in calls),
    )


async def rest_until(db: AsyncSession, action_id: UUID, *, switch_open: bool) -> datetime | None:
    """When a routine with nothing served this tick looks again — under its lock.

    Args:
        db: The tick's session, holding the routine's row lock.
        action_id: The routine.
        switch_open: The switch as the tick read it, before the lock.

    Returns:
        ``None`` (sleep until a call) when nothing waits; now when a call
        arrived since the tick's read; after the back-off when calls wait
        behind a closed switch.
    """
    if not await RoutineWebhookRepository(db).has_pending(action_id):
        return None
    now = now_utc()
    return now if switch_open else now + timedelta(seconds=ROUTINE_WEBHOOK_FAILURE_RETRY_SECONDS)


async def serve_calls(db: AsyncSession, action_id: UUID, delivery_ids: Sequence[UUID]) -> None:
    """Mark the calls a run that answered read as served, and count them.

    Args:
        db: The settle's session (committed by the tick).
        action_id: The routine.
        delivery_ids: The calls its run was shown; nothing for another clock.
    """
    if not delivery_ids:
        return
    served = await RoutineWebhookRepository(db).serve(action_id, delivery_ids, at=now_utc())
    routine_webhook_calls_served_total.inc(served)


__all__ = ["WaitingCalls", "rest_until", "serve_calls", "waiting_calls"]
