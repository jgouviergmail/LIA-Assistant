"""Accepted, unblocked relations with explicit coarse World connection presence."""

import asyncio
from uuid import UUID

from pydantic import Field

from src.core.config import settings
from src.domains.feature_switches.guard import require_capability_fresh
from src.domains.feature_switches.registry import PlatformCapability
from src.domains.peers.directory import page_connected_people
from src.domains.world.message_access import MessageAccess
from src.domains.world.messages import MailboxScope
from src.domains.world.presence import PeerPresenceStatus, peer_presence
from src.domains.world.schemas import StrictModel
from src.infrastructure.database.session import get_db_context


class PeerPageRequest(MailboxScope):
    after: str | None = Field(
        default=None,
        pattern=r"^[0-9a-f]{8}-(?:[0-9a-f]{4}-){3}[0-9a-f]{12}$",
        description="Last accepted connection identifier used to resume private directory pagination.",
    )


class PeerProxy(StrictModel):
    connection: str = Field(
        description="Accepted native peer connection identifier; never a third-party presence claim."
    )
    name: str = Field(description="Native public display name; no private profile inference.")
    presence: PeerPresenceStatus = Field(
        description="Coarse World presence from a real fenced connection; never native login or assistant activity.",
    )


class PeerPage(StrictModel):
    peers: list[PeerProxy] = Field(
        default_factory=list,
        max_length=12,
        description="Bounded coarse projections of accepted unblocked relations, including visible World actors.",
    )
    next_cursor: str | None = Field(
        default=None,
        description="Accepted-connection pagination cursor, or null at the end.",
    )


async def read_peer_page(
    access: MessageAccess, cookie: str, account: str, payload: PeerPageRequest
) -> PeerPage:
    """Page accepted connections under fresh native capability and live World authorization."""
    await access.context(cookie, account, payload)
    async with asyncio.timeout(settings.world_policy_timeout):
        async with get_db_context() as db:
            await require_capability_fresh(db, PlatformCapability.PEERS)
            page = await page_connected_people(
                db, UUID(account), after=UUID(payload.after) if payload.after else None
            )
    context = await access.context(
        cookie, account, payload, {str(item.peer_id) for item in page.items}
    )
    return PeerPage(
        peers=[
            PeerProxy(
                connection=str(item.connection_id),
                name=item.peer_display_name,
                presence=peer_presence(context.state, str(item.peer_id), context.now),
            )
            for item in page.items
            if str(item.peer_id) not in context.policy.blocked
            and str(item.peer_id) in context.policy.eligible
        ],
        next_cursor=str(page.next_cursor) if page.next_cursor else None,
    )
