"""Only the account's exact server-minted stored filename can be inspected or removed."""

import asyncio
from pathlib import Path
from uuid import UUID

from src.core.config import settings
from src.domains.agents.application.asset_file_schemas import AssetFileWitness
from src.domains.attachments.file_paths import owned_asset_path as owned_asset_path
from src.infrastructure.file_transfer import LocalFileRead


async def capture_asset_file(
    actor_id: UUID, identity: UUID, filename: str, declared_path: str
) -> AssetFileWitness:
    path = await asyncio.to_thread(owned_asset_path, actor_id, filename)
    declared = await asyncio.to_thread(
        (Path(settings.attachments_storage_path) / declared_path).resolve
    )
    if declared != path:
        raise ValueError("Stored file identity is inconsistent")
    try:
        reader = await LocalFileRead.async_open(path)
    except FileNotFoundError:
        return AssetFileWitness(id=identity, stored_filename=filename)
    try:
        return AssetFileWitness(
            id=identity, stored_filename=filename, file_digest=reader.identity_digest
        )
    finally:
        await reader.close()
