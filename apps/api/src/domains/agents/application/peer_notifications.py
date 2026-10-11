"""Post-ACK lifecycle notices own their transaction and cannot poison the saved command."""

from collections.abc import Callable, Coroutine

from pydantic import JsonValue
from sqlalchemy.ext.asyncio import AsyncSession

from src.domains.peers.schemas import PeerEvent
from src.infrastructure.database.session import get_db_context

PeerDispatcher = Callable[[list[PeerEvent], AsyncSession], Coroutine[object, object, None]]


async def notify_saved_peer_action(
    events: list[PeerEvent], dispatch: PeerDispatcher, public: dict[str, JsonValue]
) -> None:
    """Attempt source notices in their own session after the action's acknowledged commit.

    A source dispatcher can commit its archive before external delivery. Its SQL failure
    must roll back its own session, never leave the command owner's session aborted.
    """
    try:
        async with get_db_context() as db:
            await dispatch(events, db)
    except Exception:
        public["notification_status"] = "failed"
