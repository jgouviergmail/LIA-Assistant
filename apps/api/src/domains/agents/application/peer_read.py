"""Owned UI reads reuse peer consent, side-specific relay text and source scope."""

from datetime import UTC, datetime
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from src.domains.agents.application.authorization import load_actor
from src.domains.agents.application.availability import require_application_tools
from src.domains.agents.application.peer_read_schemas import (
    PeerUIItem,
    PeerUIProjection,
    PeerUIQuery,
)
from src.domains.feature_switches.guard import require_capability_fresh
from src.domains.feature_switches.registry import PlatformCapability
from src.domains.peers.constants import PEER_ACCESS_LOG_MAX_ENTRIES
from src.domains.peers.repository import PeersRepository
from src.domains.peers.schemas import DiscoveryStateResponse, RelayedMessageItem
from src.domains.peers.service import PeersService


async def read_peer_ui(db: AsyncSession, actor_id: UUID, query: PeerUIQuery) -> PeerUIProjection:
    selected = PeerUIQuery.model_validate(query.model_dump())
    await require_application_tools(db)
    await require_capability_fresh(db, PlatformCapability.PEERS)
    actor = await load_actor(db, actor_id)
    service = PeersService(db)
    preferences = None
    source_limit = None
    total = None
    available = 0
    items: list[PeerUIItem]
    if selected.section == "preferences":
        preferences = DiscoveryStateResponse(
            discovery_enabled=bool(actor.discovery_enabled),
            email_visible=bool(actor.peer_email_visible),
        )
        items = []
    elif selected.section == "messages":
        repo = PeersRepository(db)
        activity = await repo.list_delivered_message_activity(
            actor_id, limit=selected.limit, offset=selected.offset
        )
        items = [
            RelayedMessageItem(
                id=str(item.message_id),
                peer_display_name=item.peer_display_name,
                direction=item.direction,
                content=item.text,
                occurred_at=item.occurred_at,
            )
            for item in activity
        ]
        total = await repo.count_delivered_messages(actor_id)
        available = total
    else:
        rows = await _peer_ui_rows(service, actor_id, selected.section)
        if selected.section == "access_log":
            source_limit = PEER_ACCESS_LOG_MAX_ENTRIES
        else:
            total = len(rows)
        available = len(rows)
        items = rows[selected.offset : selected.offset + selected.limit]
    await require_application_tools(db)
    await require_capability_fresh(db, PlatformCapability.PEERS)
    await load_actor(db, actor_id)
    next_offset = selected.offset + selected.limit
    result = PeerUIProjection(
        section=selected.section,
        preferences=preferences,
        items=items,
        total=total,
        next_offset=next_offset if next_offset < available else None,
        source_limit=source_limit,
        observed_at=datetime.now(UTC),
    )
    if len(result.model_dump_json().encode("utf-8")) > 64_000:
        raise ValueError("Peer UI response exceeds the bounded native result; use a smaller page")
    return result


async def _peer_ui_rows(service: PeersService, actor_id: UUID, section: str) -> list[PeerUIItem]:
    if section == "connections":
        return list(await service.get_connections(actor_id))
    if section == "requests":
        return list(await service.get_pending(actor_id))
    if section == "blocks":
        return list(await service.list_blocks(actor_id))
    if section == "access_log":
        return list(await service.get_access_log(actor_id, limit=PEER_ACCESS_LOG_MAX_ENTRIES))
    raise ValueError("Unsupported peer UI section")
