"""The latest calls LIA placed to a person's numbers (2026-11-07).

The contacts tool's « Latest exchanges » shows the calls LIA placed to a contact. A callee's number
is stored encrypted and keyed by nothing a query could match, so it cannot be looked up: the
account's latest calls to someone else (``CallKind.THIRD_PARTY``: never the owner's own, nor a
verification) are read newest first under a bound and matched by the domain's rule for « the same
line » (``same_line``), which lets a contact written nationally find a call dialled in E.164. When
the bound hid older calls and the list is not full, the cut is said.

What a line carries is what a list of exchanges shows: when, how it went, what it was for. The
number never leaves this module, and nothing here reaches a model or a register: it is the person
reading LIA's own records.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from datetime import datetime
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.exceptions import ExternalServiceError
from src.core.security import decrypt_data
from src.domains.feature_switches.guard import require_capability_fresh
from src.domains.feature_switches.registry import PlatformCapability
from src.domains.telephony.models import CallKind, PhoneCall, PhoneCallOutcome, PhoneCallStatus
from src.domains.telephony.phone_numbers import same_line


@dataclass(frozen=True, slots=True)
class PlacedCall:
    """A call LIA placed, as a list of exchanges shows it: never its number."""

    id: UUID
    at: datetime
    status: PhoneCallStatus
    outcome: PhoneCallOutcome | None
    seconds: float | None
    purpose: str


@dataclass(frozen=True, slots=True)
class CallsToLines:
    """The latest calls to a person's numbers, and whether the bound hid older ones."""

    calls: list[PlacedCall]
    cut: bool


async def calls_to_lines(
    db: AsyncSession, owner: UUID, numbers: Sequence[str], *, limit: int, scan: int
) -> CallsToLines | None:
    """The latest calls LIA placed to any of these numbers.

    Args:
        db: A session the caller owns; nothing here waits on the network.
        owner: The account.
        numbers: The person's numbers, written however they were saved.
        limit: How many calls the list holds.
        scan: How many of the account's latest calls to someone else are read.

    Returns:
        The calls, newest first, with ``cut`` when more calls than ``scan`` were placed and fewer
        than ``limit`` matched; None when LIA never placed a call to anyone for this account.

    Raises:
        AuthorizationError: Telephony is switched off (``CAPABILITY_DISABLED``), as the calls list
            refuses it.
        ExternalServiceError: A stored number cannot be read: never a call silently left out.
    """
    await require_capability_fresh(db, PlatformCapability.TELEPHONY)
    rows = list(
        (
            await db.scalars(
                select(PhoneCall)
                .where(PhoneCall.user_id == owner, PhoneCall.call_kind == CallKind.THIRD_PARTY)
                .order_by(PhoneCall.created_at.desc(), PhoneCall.id.desc())
                .limit(scan + 1)
            )
        ).all()
    )
    if not rows:
        return None
    found = [_placed(call) for call in rows[:scan] if _to_any(call, numbers)][:limit]
    return CallsToLines(calls=found, cut=len(rows) > scan and len(found) < limit)


def _to_any(call: PhoneCall, numbers: Sequence[str]) -> bool:
    try:
        dialled = decrypt_data(call.callee_phone)
    except ValueError:
        raise ExternalServiceError("telephony", detail="CALL_NUMBER_UNAVAILABLE") from None
    return any(same_line(dialled, number) for number in numbers)


def _placed(call: PhoneCall) -> PlacedCall:
    return PlacedCall(
        id=call.id,
        at=call.created_at,
        status=call.status,
        outcome=call.outcome,
        seconds=float(call.call_seconds) if call.call_seconds is not None else None,
        purpose=call.objective,
    )


__all__ = ["CallsToLines", "PlacedCall", "calls_to_lines"]
