"""Bounded metadata witnesses omit extracted document bodies from retention reads."""

from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from src.core.config import settings
from src.domains.agents.application.asset_metadata import owned_generated_metadata
from src.domains.agents.application.asset_retention_schemas import (
    ASSET_RETENTION_MAX_BYTES,
    AssetRetentionInput,
    AssetRetentionSelection,
)
from src.domains.agents.application.command_service import CommandRejected
from src.domains.agents.effects.digest import payload_digest
from src.domains.attachments.keep import keep_usage
from src.domains.attachments.schemas import GeneratedAssetKeepUsage, GeneratedAssetSummary


async def asset_retention_selection(
    db: AsyncSession, actor_id: UUID, request: AssetRetentionInput, *, lock: bool = False
) -> AssetRetentionSelection:
    ordered = await owned_generated_metadata(db, actor_id, request.ids, lock=lock)
    selected = AssetRetentionSelection(
        request=request,
        items=tuple(GeneratedAssetSummary.model_validate(row) for row in ordered),
        usage=GeneratedAssetKeepUsage.model_validate(await keep_usage(db, actor_id)),
        ttl_hours=settings.attachments_ttl_hours,
        state_digest=payload_digest({"items": ordered}),
    )
    if len(selected.model_dump_json().encode("utf-8")) > ASSET_RETENTION_MAX_BYTES:
        raise CommandRejected("CONSTRAINT_VIOLATION")
    return selected
