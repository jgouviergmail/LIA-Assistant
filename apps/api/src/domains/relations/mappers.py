"""How each record of a relationship reads on its card — ONE wording for every view.

The 360° card's sections and the relationship timeline show the same records;
mapped twice, a commitment could read one way in its section and another in
the timeline. Both map here.
"""

from __future__ import annotations

from datetime import datetime
from typing import TYPE_CHECKING

from src.domains.open_loops.models import OpenLoop
from src.domains.relations.schemas import RelationCall, RelationOpenLoop, RelationPeerMessage
from src.domains.telephony.models import PhoneCall

if TYPE_CHECKING:
    from src.domains.relations.peer_messages import PeerMessageSignal


def days_between(then: datetime, now: datetime) -> int:
    return max(0, (now - then).days)


def to_open_loop(loop: OpenLoop, now: datetime) -> RelationOpenLoop:
    """Map one open-loop row onto the API contract."""
    return RelationOpenLoop(
        id=str(loop.id),
        subject=loop.subject,
        direction=loop.direction,
        due_hint=loop.due_hint,
        days_open=days_between(loop.created_at, now),
        opened_at=loop.created_at,
    )


def to_call(call: PhoneCall) -> RelationCall:
    """Map one phone-call row onto the API contract (never the number — D-8)."""
    return RelationCall(
        id=str(call.id),
        objective=call.objective,
        outcome=call.outcome.value if call.outcome else None,
        summary=call.summary,
        created_at=call.created_at,
    )


def to_peer_message(signal: PeerMessageSignal) -> RelationPeerMessage:
    """Map one bridge signal onto the API contract."""
    return RelationPeerMessage(
        id=signal.message_id,
        direction=signal.direction,
        content=signal.content,
        occurred_at=signal.occurred_at,
    )


__all__ = ["days_between", "to_call", "to_open_loop", "to_peer_message"]
