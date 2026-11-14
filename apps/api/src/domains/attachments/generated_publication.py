"""Generated files use the same durable, joined publication as uploaded files."""

from collections.abc import Sequence
from functools import partial
from pathlib import Path
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from src.core.conversation_execution import ExecutionRevoked
from src.core.run_authority import current_run_authority
from src.domains.attachments.file_contracts import FileWriteResult, UploadMetadata
from src.domains.attachments.file_publication import FilePublication, publish_files
from src.domains.attachments.models import Attachment


def _write_bytes(data: bytes, path: Path) -> FileWriteResult:
    """Allocate only the repository's path, off-loop, then report the actual size."""
    path.parent.mkdir(parents=True, exist_ok=True)
    written = path.write_bytes(data)
    if written != len(data):
        raise OSError("Incomplete generated file write")
    return FileWriteResult(written)


async def publish_generated_files(
    db: AsyncSession, *, owner_id: UUID, files: Sequence[tuple[UploadMetadata, bytes]]
) -> list[Attachment]:
    """Keep the producing turn's exact generation; unbound producers name no discussion."""
    authority = current_run_authority()
    target = authority.admission.target if authority is not None else None
    if authority is not None:
        authority.require_current()
    for metadata, _ in files:
        if metadata.conversation_id is not None and (
            target is None or metadata.conversation_id != target.id or target.owner_id != owner_id
        ):
            raise ExecutionRevoked()
    return await publish_files(
        db,
        owner_id=owner_id,
        target=target,
        files=[FilePublication(metadata, partial(_write_bytes, data)) for metadata, data in files],
    )
