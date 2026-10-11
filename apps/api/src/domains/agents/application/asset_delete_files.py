"""Only the account's exact server-minted stored filename can be inspected or removed."""

import asyncio
from pathlib import Path
from uuid import UUID

from src.core.config import settings
from src.domains.agents.application.asset_file_schemas import AssetFileWitness
from src.infrastructure.file_transfer import LocalFileRead


def owned_asset_path(actor_id: UUID, filename: str) -> Path:
    root = Path(settings.attachments_storage_path).resolve()
    account = root / str(actor_id)
    path = account / filename
    if not filename or Path(filename).name != filename or "\\" in filename:
        raise ValueError("Invalid stored file name")
    if (
        account.is_symlink()
        or path.is_symlink()
        or account.resolve() != account
        or path.resolve().parent != account
    ):
        raise ValueError("Invalid owned file location")
    return path


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


async def cleanup_asset_file(actor_id: UUID, file: AssetFileWitness) -> bool:
    try:
        path = await asyncio.to_thread(owned_asset_path, actor_id, file.stored_filename)
        reader = await LocalFileRead.async_open(path)
    except FileNotFoundError:
        return True
    except OSError, ValueError:
        return False
    try:
        same = file.file_digest is not None and reader.identity_digest == file.file_digest
    finally:
        await reader.close()
    if not same:
        return False
    try:
        await asyncio.to_thread(path.unlink)
        return True
    except FileNotFoundError:
        return True
    except OSError:
        return False
