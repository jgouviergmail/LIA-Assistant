"""A webhook routine's address and secret: drawn, carried along a clock change, shown.

ADR-386. The address and its secret are the SERVER's: drawn here when a routine
starts running on calls, erased when it stops (the calls still waiting go with
them: no run of another clock reads them), and composed into the URL another
system calls. The secret is stored encrypted and never served again after the
answer of the request that drew it.

Running on calls is a capability an operator can close (``ROUTINE_WEBHOOKS``):
a routine cannot START running on calls while it is closed, read fresh from the
database because this is a write (``require_capability_fresh``); a routine that
already does keeps its record (ADR-280).
"""

from __future__ import annotations

from typing import Any
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from src.core.security.utils import encrypt_data
from src.domains.feature_switches.guard import require_capability_fresh
from src.domains.feature_switches.registry import PlatformCapability
from src.domains.scheduled_actions.models import TriggerKind
from src.domains.scheduled_actions.webhook_repository import RoutineWebhookRepository
from src.domains.scheduled_actions.webhooks import draw_webhook_key, draw_webhook_secret

#: The columns that hold a routine's address — None on every other clock.
_NO_ADDRESS: dict[str, Any] = {"webhook_key": None, "webhook_secret": None}


def encrypted_secret(secret: str) -> str:
    """The form a secret is stored in."""
    return encrypt_data(secret)


async def address_on_entry(db: AsyncSession) -> dict[str, Any]:
    """A new address and secret for a routine starting to run on calls.

    Args:
        db: The writer's session, for the operator's switch read fresh.

    Returns:
        The column values: the key, and the secret encrypted. The secret drawn
        here is never shown; its owner draws the one they will hand out.

    Raises:
        AuthorizationError: When the capability is closed on this instance.
    """
    await require_capability_fresh(db, PlatformCapability.ROUTINE_WEBHOOKS)
    return {
        "webhook_key": draw_webhook_key(),
        "webhook_secret": encrypted_secret(draw_webhook_secret()),
    }


async def address_change(
    db: AsyncSession, *, action_id: UUID, stored_kind: str, resulting_kind: str
) -> dict[str, Any]:
    """What a clock change does to a routine's address, and to the calls it kept.

    Args:
        db: The writer's session.
        action_id: The routine.
        stored_kind: Its clock before the change.
        resulting_kind: Its clock after.

    Returns:
        The column values to write: a new address on entry, none on exit,
        nothing when the routine stays on (or off) calls.

    Raises:
        AuthorizationError: On entry, when the capability is closed.
    """
    webhook = TriggerKind.WEBHOOK.value
    if resulting_kind == webhook and stored_kind != webhook:
        return await address_on_entry(db)
    if stored_kind == webhook and resulting_kind != webhook:
        # Under the routine's row lock, the one the door's write takes: a call
        # landing between the forgetting and the clock change would otherwise be
        # kept for a routine that no longer reads calls. The door waits, then
        # finds no address.
        repository = RoutineWebhookRepository(db)
        await repository.lock_routine(action_id)
        await repository.discard(action_id)
        return dict(_NO_ADDRESS)
    return {}


__all__ = ["address_change", "address_on_entry", "encrypted_secret"]
