"""Private complete source/parent and streamed document identity witnesses."""

import hashlib
from uuid import UUID

from pydantic import JsonValue, TypeAdapter
from sqlalchemy import func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.constants import RAG_SOURCE_IDENTITY_BATCH_ROWS
from src.core.exceptions import AuthorizationError, raise_not_found_or_unauthorized
from src.domains.agents.application.command_service import CommandRejected
from src.domains.agents.application.source_unlink_schemas import (
    SourceUnlinkInput,
    SourceUnlinkSelection,
)
from src.domains.agents.application.space_update import _source_row
from src.domains.agents.application.space_update_schemas import SpaceUpdateTarget
from src.domains.agents.effects.digest import payload_digest
from src.domains.rag_spaces.models import (
    RAGDocument,
    RAGDriveSource,
    RAGMailSource,
    RAGSourceSyncStatus,
)
from src.domains.rag_spaces.ui_queries import owned_space

_SOURCE = TypeAdapter(dict[str, JsonValue])


async def document_id_digest(db: AsyncSession, space_id: UUID) -> str:
    digest = hashlib.sha256()
    rows = await db.stream_scalars(
        select(RAGDocument.id)
        .where(RAGDocument.space_id == space_id)
        .order_by(RAGDocument.id)
        .execution_options(yield_per=RAG_SOURCE_IDENTITY_BATCH_ROWS)
    )
    try:
        async for identity in rows:
            digest.update(identity.bytes)
    finally:
        await rows.close()
    return digest.hexdigest()


async def source_unlink_selection(
    db: AsyncSession, actor_id: UUID, request: SourceUnlinkInput, *, lock: bool = False
) -> SourceUnlinkSelection:
    space = await owned_space(db, actor_id, request.space_id)
    model = RAGDriveSource if request.kind == "drive" else RAGMailSource
    predicate = (
        model.id == request.source_id,
        model.space_id == request.space_id,
        model.user_id == actor_id,
    )
    if lock and await db.scalar(select(model.id).where(*predicate).with_for_update()) is None:
        raise_not_found_or_unauthorized("source", request.source_id)
    value = await db.scalar(select(func.to_jsonb(model.__table__.table_valued())).where(*predicate))
    if value is None:
        raise_not_found_or_unauthorized("source", request.source_id)
    raw = _SOURCE.validate_python(value)
    if raw["sync_status"] not in {
        RAGSourceSyncStatus.IDLE,
        RAGSourceSyncStatus.COMPLETED,
        RAGSourceSyncStatus.ERROR,
    }:
        raise CommandRejected("CONSTRAINT_VIOLATION")
    name = raw["folder_name" if request.kind == "drive" else "label_name"]
    if not isinstance(name, str) or not isinstance(raw["sync_status"], str):
        raise ValueError("Invalid source metadata")
    reference = (
        RAGDocument.drive_source_id if request.kind == "drive" else RAGDocument.mail_source_id
    )
    invalid = await db.scalar(
        select(func.count(RAGDocument.id)).where(
            reference == request.source_id,
            or_(
                RAGDocument.user_id != actor_id,
                RAGDocument.user_id.is_(None),
                RAGDocument.space_id != request.space_id,
            ),
        )
    )
    if invalid:
        raise AuthorizationError(detail={"error_code": "FORBIDDEN"})
    count = int(
        await db.scalar(select(func.count(RAGDocument.id)).where(reference == request.source_id))
        or 0
    )
    documents = await document_id_digest(db, request.space_id)
    return SourceUnlinkSelection(
        request=request,
        space=SpaceUpdateTarget.model_validate(space),
        source_name=name,
        sync_status=raw["sync_status"],
        documents=count,
        documents_digest=documents,
        state_digest=payload_digest(
            {
                "source": raw,
                "space": await _source_row(db, actor_id, request.space_id),
                "documents": documents,
            }
        ),
    )
