"""Own the live peer-delivery lease, and cancel all work when it is lost."""

import asyncio
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

import structlog

from src.core.config import settings
from src.core.constants import PEERS_DELIVERY_RENEWAL_DIVISOR
from src.domains.peers.delivery_repository import (
    DeliveryClaim,
    DeliveryLeaseLost,
    PeerDeliveryRepository,
)
from src.infrastructure.async_utils import cancel_and_join
from src.infrastructure.database.session import get_db_context

logger = structlog.get_logger(__name__)


@asynccontextmanager
async def delivery_lease(claim: DeliveryClaim) -> AsyncIterator[None]:
    """Renew on independent short sessions; stop and await the owned pump."""
    parent = asyncio.current_task()
    assert parent is not None
    lost = asyncio.Event()

    async def pump() -> None:
        try:
            while True:
                await asyncio.sleep(
                    settings.peers_delivery_lease_seconds / PEERS_DELIVERY_RENEWAL_DIVISOR
                )
                async with get_db_context() as db:
                    renewed = await PeerDeliveryRepository(db).renew(claim)
                if not renewed:
                    break
        except Exception as error:
            logger.warning(
                "peer_delivery_renew_failed",
                message_id=str(claim.message_id),
                error_type=type(error).__name__,
            )
        lost.set()
        parent.cancel()

    task = asyncio.create_task(pump(), name=f"peer_delivery_lease_{claim.message_id}")
    try:
        yield
    except asyncio.CancelledError:
        if lost.is_set():
            raise DeliveryLeaseLost("Peer delivery lease lost") from None
        raise
    finally:
        await cancel_and_join(task)
