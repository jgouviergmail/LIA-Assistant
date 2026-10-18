"""Read-only cross-domain origin projection through the registered SQL metadata.

The installers depend on skills/plugins/MCP. Their UI readers cannot depend
back on peers: a shared Core projection keeps that dependency one-way.
"""

from collections.abc import Iterable
from uuid import UUID

from sqlalchemy import case, select
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.capability_origin import CapabilityOrigin, CapabilityOriginKind
from src.infrastructure.database.session import Base


class _OriginRecord(CapabilityOrigin):
    resource_id: UUID


async def capability_origins(
    db: AsyncSession,
    owner_id: UUID,
    kind: CapabilityOriginKind,
    resource_ids: Iterable[UUID],
) -> dict[UUID, CapabilityOrigin]:
    ids = tuple(resource_ids)
    if not ids:
        return {}
    components = Base.metadata.tables["peer_capability_components"]
    transfers = Base.metadata.tables["peer_capability_transfers"]
    users = Base.metadata.tables["users"]
    sender_name = case(
        (users.c.deleted_at.is_(None) & users.c.is_active.is_(True), users.c.full_name),
        else_=None,
    )
    query = select(
        components.c.resource_id.label("resource_id"),
        sender_name.label("sender_display_name"),
        transfers.c.transferred_at.label("shared_at"),
        transfers.c.id.label("transfer_id"),
    )
    query = query.select_from(
        components.join(transfers, transfers.c.id == components.c.transfer_id).outerjoin(
            users, users.c.id == transfers.c.sender_id
        )
    ).where(
        components.c.kind == kind,
        components.c.installed.is_(True),
        components.c.resource_id.in_(ids),
        transfers.c.recipient_id == owner_id,
        transfers.c.transferred_at.is_not(None),
    )
    records = [_OriginRecord.model_validate(row) for row in (await db.execute(query)).mappings()]
    return {
        record.resource_id: CapabilityOrigin(
            sender_display_name=record.sender_display_name,
            shared_at=record.shared_at,
            transfer_id=record.transfer_id,
        )
        for record in records
    }
