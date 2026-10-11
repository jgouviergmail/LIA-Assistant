"""Whole owned generated selection reuses metadata and sealed local file observations."""

import asyncio
from pathlib import Path
from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.config import settings
from src.domains.agents.application.asset_delete_files import capture_asset_file
from src.domains.agents.application.asset_delete_schemas import (
    ASSET_DELETE_MAX_BYTES,
    AssetDeleteInput,
    AssetDeleteSelection,
)
from src.domains.agents.application.asset_metadata import owned_generated_metadata
from src.domains.agents.application.command_service import CommandRejected
from src.domains.agents.effects.digest import payload_digest
from src.domains.attachments.models import Attachment
from src.domains.attachments.schemas import GeneratedAssetSummary


async def asset_deletion_selection(
    db: AsyncSession, actor_id: UUID, request: AssetDeleteInput, *, lock: bool = False
) -> AssetDeleteSelection:
    rows = await owned_generated_metadata(db, actor_id, request.ids, lock=lock)
    files = []
    aliases: set[str] = set()
    root = await asyncio.to_thread(Path(settings.attachments_storage_path).resolve)
    for row in rows:
        name, declared = row["stored_filename"], row["file_path"]
        if not isinstance(name, str) or not isinstance(declared, str):
            raise CommandRejected("INVALID_INPUT")
        file = await capture_asset_file(actor_id, UUID(str(row["id"])), name, declared)
        aliases.update(
            {
                declared,
                str(root / str(actor_id) / name),
                f"{actor_id}/{name}",
                str(Path(str(actor_id)) / name),
            }
        )
        files.append(file)
    if await db.scalar(
        select(func.count(Attachment.id)).where(
            Attachment.file_path.in_(aliases), Attachment.id.not_in(request.ids)
        )
    ):
        raise CommandRejected("CONSTRAINT_VIOLATION")
    selected = AssetDeleteSelection(
        request=request,
        items=tuple(GeneratedAssetSummary.model_validate(row) for row in rows),
        files=tuple(files),
        state_digest=payload_digest({"items": rows}),
    )
    if len(selected.model_dump_json().encode("utf-8")) > ASSET_DELETE_MAX_BYTES:
        raise CommandRejected("CONSTRAINT_VIOLATION")
    return selected
