"""Read exact generated metadata and open only the account's sealed regular file."""

import asyncio
from pathlib import Path
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from src.core.config import settings
from src.domains.agents.application.asset_delete_files import owned_asset_path
from src.domains.agents.application.asset_download_schemas import (
    AssetDownloadInput,
    AssetDownloadSnapshot,
)
from src.domains.agents.application.asset_file_schemas import AssetFileWitness
from src.domains.agents.application.asset_metadata import owned_generated_metadata
from src.domains.agents.application.command_service import CommandRejected
from src.domains.agents.effects.digest import payload_digest
from src.domains.attachments.models import AttachmentStatus
from src.domains.attachments.schemas import GeneratedAssetSummary
from src.infrastructure.file_transfer import LocalFileRead


async def open_asset_snapshot(
    db: AsyncSession, actor_id: UUID, request: AssetDownloadInput, *, lock: bool = False
) -> tuple[AssetDownloadSnapshot, LocalFileRead]:
    row = (await owned_generated_metadata(db, actor_id, (request.asset_id,), lock=lock))[0]
    if row["status"] != AttachmentStatus.READY:
        raise CommandRejected("NOT_FOUND_OR_UNAUTHORIZED")
    name, declared = row["stored_filename"], row["file_path"]
    if not isinstance(name, str) or not isinstance(declared, str):
        raise CommandRejected("INVALID_INPUT")
    path = await asyncio.to_thread(owned_asset_path, actor_id, name)
    actual = await asyncio.to_thread((Path(settings.attachments_storage_path) / declared).resolve)
    if actual != path:
        raise CommandRejected("STALE_STATE")
    try:
        reader = await LocalFileRead.async_open(path)
    except OSError, ValueError:
        raise CommandRejected("NOT_FOUND_OR_UNAUTHORIZED") from None
    try:
        if reader.file_size_bytes != row["file_size"]:
            raise CommandRejected("STALE_STATE")
        return (
            AssetDownloadSnapshot(
                request=request,
                item=GeneratedAssetSummary.model_validate(row),
                file=AssetFileWitness(
                    id=request.asset_id, stored_filename=name, file_digest=reader.identity_digest
                ),
                state_digest=payload_digest({"item": row}),
            ),
            reader,
        )
    except BaseException:
        await reader.close()
        raise
