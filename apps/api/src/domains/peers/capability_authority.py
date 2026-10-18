"""Fresh pair/feature authority and serialized transfer admission."""

from datetime import UTC, datetime
from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.config import settings
from src.core.exceptions import (
    AuthorizationError,
    ResourceNotFoundError,
    raise_rate_limit_exceeded,
)
from src.domains.feature_switches.guard import require_capability_fresh
from src.domains.feature_switches.registry import PlatformCapability
from src.domains.peers.capability_contracts import CapabilityKind
from src.domains.peers.capability_models import PeerCapabilityTransfer
from src.domains.peers.models import PeerConnectionStatus
from src.domains.peers.pair_fence import lock_peer_pair
from src.domains.peers.repository import PeersRepository, utc_day_bounds
from src.domains.users.models import User

_CAPABILITIES = {
    CapabilityKind.SKILL: (PlatformCapability.PEERS, PlatformCapability.SKILLS),
    CapabilityKind.MCP: (PlatformCapability.PEERS, PlatformCapability.MCP),
    CapabilityKind.PLUGIN: (PlatformCapability.PEERS, PlatformCapability.SKILLS),
}


def _required_capabilities(
    kind: CapabilityKind, mcp_required: bool
) -> tuple[PlatformCapability, ...]:
    additional = (PlatformCapability.MCP,) if kind is CapabilityKind.PLUGIN and mcp_required else ()
    return _CAPABILITIES[kind] + additional


async def capability_authority(
    db: AsyncSession,
    sender: UUID,
    connection_id: UUID | None,
    kind: CapabilityKind,
    *,
    lock: bool = False,
    mcp_required: bool = False,
) -> UUID:
    if kind is CapabilityKind.PLUGIN and not settings.plugins_enabled:
        raise AuthorizationError(detail="peers_capability_disabled")
    pair = await PeersRepository(db).get_by_id(connection_id) if connection_id else None
    if pair is None or sender not in {pair.user_a_id, pair.user_b_id}:
        raise ResourceNotFoundError("capability")
    recipient = pair.user_b_id if pair.user_a_id == sender else pair.user_a_id
    if lock:
        await lock_peer_pair(db, sender, recipient)
        pair = await PeersRepository(db).get_by_id(pair.id, for_update=True)
    if pair is None or pair.status != PeerConnectionStatus.ACCEPTED.value:
        raise ResourceNotFoundError("capability")
    if await PeersRepository(db).has_block_between(sender, recipient):
        raise ResourceNotFoundError("capability")
    active = (
        await db.scalars(
            select(User.id).where(
                User.id.in_({sender, recipient}),
                User.is_active.is_(True),
                User.deleted_at.is_(None),
            )
        )
    ).all()
    if len(active) != 2:
        raise ResourceNotFoundError("capability")
    for capability in _required_capabilities(kind, mcp_required):
        await require_capability_fresh(db, capability)
    return recipient


async def check_transfer_caps(db: AsyncSession, sender: UUID, recipient: UUID, size: int) -> None:
    start, end = utc_day_bounds(datetime.now(UTC))
    scopes = (
        (
            PeerCapabilityTransfer.sender_id == sender,
            settings.peers_capability_sender_daily_limit,
        ),
        (
            (PeerCapabilityTransfer.sender_id == sender)
            & (PeerCapabilityTransfer.recipient_id == recipient),
            settings.peers_capability_pair_daily_limit,
        ),
        (
            PeerCapabilityTransfer.recipient_id == recipient,
            settings.peers_capability_recipient_daily_limit,
        ),
    )
    for predicate, maximum in scopes:
        count, total_bytes = (
            await db.execute(
                select(
                    func.count(),
                    func.coalesce(func.sum(PeerCapabilityTransfer.payload_bytes), 0),
                ).where(
                    predicate,
                    PeerCapabilityTransfer.created_at >= start,
                    PeerCapabilityTransfer.created_at < end,
                )
            )
        ).one()
        if count >= maximum or total_bytes + size > settings.peers_capability_daily_bytes:
            raise_rate_limit_exceeded(
                maximum,
                86400,
                max(1, int((end - datetime.now(UTC)).total_seconds())),
                detail="peers_capability_quota_reached",
            )
