"""Prepare an exclusive destination copy after consent; keep originals through unknown SQL ACK."""

import asyncio
import os
from dataclasses import dataclass
from pathlib import Path
from uuid import UUID

from src.domains.rag_spaces.document_access import owned_document_path
from src.domains.rag_spaces.document_deletion_cleanup import cleanup_deleted_document_file
from src.infrastructure.file_transfer import LocalFileRead


@dataclass(frozen=True)
class StagedDocumentFile:
    actor_id: UUID
    source_space_id: UUID
    target_space_id: UUID
    filename: str
    source_digest: str
    target_digest: str


def _path(actor_id: UUID, space_id: UUID, filename: str) -> Path:
    if (
        not filename
        or any(character in filename for character in "/\\:")
        or any(ord(character) < 32 for character in filename)
    ):
        raise ValueError("Choose a literal stored filename")
    selected = owned_document_path(actor_id, space_id, filename)
    if selected is None:
        raise ValueError("Document relocation requires an exact owned regular-file path")
    return selected


def destination_taken(actor_id: UUID, space_id: UUID, filename: str) -> bool:
    """Whether a move would land on an existing entry — run it in a worker thread."""
    return os.path.lexists(_path(actor_id, space_id, filename))


def _staging_paths(
    actor_id: UUID, source_space_id: UUID, target_space_id: UUID, filename: str
) -> tuple[Path, Path]:
    """Both exact paths, the destination still free — run it in a worker thread."""
    source = _path(actor_id, source_space_id, filename)
    destination = _path(actor_id, target_space_id, filename)
    if os.path.lexists(destination):
        raise FileExistsError("Document destination already exists")
    return source, destination


async def rollback_staged_file(staged: StagedDocumentFile) -> bool:
    """Before known rollback only, remove the exact copy created by this operation."""
    return await cleanup_deleted_document_file(
        staged.actor_id, staged.target_space_id, staged.filename, staged.target_digest
    )


async def _rollback_created_file(
    actor_id: UUID, target_space_id: UUID, filename: str, identity: tuple[int, int]
) -> bool:
    """Even a failed flush owns only the newly opened inode, never a replacement."""
    try:
        reader = LocalFileRead.open(_path(actor_id, target_space_id, filename))
    except FileNotFoundError:
        return True
    except OSError, ValueError:
        return False
    try:
        if reader.creation_identity != identity:
            return False
        digest = reader.identity_digest
    finally:
        await reader.close()
    return await cleanup_deleted_document_file(actor_id, target_space_id, filename, digest)


async def stage_document_file(
    actor_id: UUID,
    source_space_id: UUID,
    target_space_id: UUID,
    filename: str,
    expected_digest: str | None,
    file_size: int,
) -> StagedDocumentFile | None:
    if source_space_id == target_space_id or file_size < 0:
        raise ValueError("Choose distinct owned spaces and a nonnegative observed size")
    source, destination = await asyncio.to_thread(
        _staging_paths, actor_id, source_space_id, target_space_id, filename
    )
    try:
        reader = LocalFileRead.open(source)
    except FileNotFoundError:
        if expected_digest is None:
            return None
        raise ValueError("Observed document file disappeared") from None
    created_identity: tuple[int, int] | None = None
    try:
        if reader.identity_digest != expected_digest or reader.file_size_bytes != file_size:
            raise ValueError("Document file changed since consent")
        await reader.freeze(max_bytes=file_size)
        destination.parent.mkdir(parents=True, exist_ok=True)
        _path(actor_id, target_space_id, filename)
        output = destination.open("xb")
        copied_size = 0
        try:
            created = os.fstat(output.fileno())
            created_identity = (created.st_dev, created.st_ino)
            await reader.copy_to(output)
        finally:
            # Copy runs in a worker. Wait for it before closing its destination,
            # including when the requesting task is cancelled mid-write.
            try:
                await reader.close()
            finally:
                try:
                    output.flush()
                    copied_size = os.fstat(output.fileno()).st_size
                finally:
                    output.close()
        if copied_size != file_size:
            raise ValueError("Destination copy differs from the approved file size")
        # Windows may finalize a file's write timestamps when the writer
        # closes. Bind the stable post-close metadata to the created inode.
        observed = LocalFileRead.open(_path(actor_id, target_space_id, filename))
        try:
            if observed.creation_identity != created_identity:
                raise ValueError("Created destination was replaced")
            return StagedDocumentFile(
                actor_id,
                source_space_id,
                target_space_id,
                filename,
                expected_digest,
                observed.identity_digest,
            )
        finally:
            await observed.close()
    except BaseException:
        if created_identity is not None:
            await _rollback_created_file(actor_id, target_space_id, filename, created_identity)
        raise
    finally:
        await reader.close()
