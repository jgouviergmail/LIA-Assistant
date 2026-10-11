"""Exact selected-document deletion uses the source transaction and acknowledges before cleanup."""

import asyncio
from datetime import UTC, datetime
from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.exceptions import ResourceConflictError
from src.domains.agents.application.action_preparation import build_action_content
from src.domains.agents.application.command_service import CommandRejected
from src.domains.agents.application.document_delete_schemas import (
    DocumentDeleteInput,
    DocumentDeletePatch,
    DocumentDeleteSelection,
    canonical_document_deletion,
)
from src.domains.agents.application.document_delete_scope import (
    document_deletion_selection,
    lock_document_deletion,
)
from src.domains.agents.application.document_delete_spec import DOCUMENT_DELETE_OPERATION
from src.domains.agents.application.draft_models import ApplicationActionDraftContent
from src.domains.agents.application.space_delete import _access
from src.domains.rag_spaces.document_deletion_cleanup import cleanup_deleted_document_file
from src.domains.rag_spaces.models import RAGChunk, RAGDocument
from src.domains.rag_spaces.service import RAGSpaceService
from src.domains.users.preference_cas import PreferenceWriteReceipt
from src.infrastructure.observability.logging import get_logger
from src.infrastructure.observability.metrics_rag_spaces import rag_documents_total_count

logger = get_logger(__name__)


async def prepare_document_deletion(
    db: AsyncSession,
    actor_id: UUID,
    request: DocumentDeleteInput,
    *,
    command_id: UUID | None = None,
) -> ApplicationActionDraftContent:
    selected = DocumentDeleteInput.model_validate(request.model_dump())
    await _access(db, actor_id)
    scope = await document_deletion_selection(db, actor_id, selected)
    await _access(db, actor_id)
    return build_action_content(
        actor_id,
        DOCUMENT_DELETE_OPERATION,
        DocumentDeletePatch(documents_to_delete=scope),
        {"documents_to_delete": scope.public_scope()},
        {"documents_to_delete": scope.public_scope(after=True)},
        command_id=command_id,
    )


async def _verify_deleted_documents(db: AsyncSession, selected: DocumentDeleteSelection) -> None:
    identities = selected.request.document_ids
    documents = await db.scalar(
        select(func.count(RAGDocument.id)).where(RAGDocument.id.in_(identities))
    )
    chunks = await db.scalar(
        select(func.count(RAGChunk.id)).where(RAGChunk.document_id.in_(identities))
    )
    total = await db.scalar(
        select(func.count(RAGDocument.id)).where(RAGDocument.space_id == selected.space.id)
    )
    if documents or chunks or total != selected.space_documents - len(identities):
        raise ResourceConflictError("document_delete", detail={"error_code": "STALE_STATE"})


async def _cleanup(actor_id: UUID, expected: DocumentDeleteSelection) -> bool:
    complete = True
    for file in expected.files:
        try:
            cleaned = await cleanup_deleted_document_file(
                actor_id, expected.space.id, file.stored_filename, file.file_digest
            )
        except (Exception, asyncio.CancelledError) as error:
            logger.warning("document_file_cleanup_pending", error_type=type(error).__name__)
            cleaned = False
        complete = complete and cleaned
    for item in expected.items:
        try:
            rag_documents_total_count.labels(status=item.status).dec()
        except Exception as error:
            logger.warning("document_deletion_telemetry_failed", error_type=type(error).__name__)
    return complete


async def execute_document_deletion(
    db: AsyncSession,
    actor_id: UUID,
    draft: ApplicationActionDraftContent,
    receipt: PreferenceWriteReceipt,
) -> None:
    if draft.actor_id != actor_id or draft.operation_id != DOCUMENT_DELETE_OPERATION.operation_id:
        raise CommandRejected("FORBIDDEN")
    if not canonical_document_deletion(draft):
        raise ValueError("Document deletion requires canonical exact consent")
    selected = DocumentDeletePatch.model_validate(draft.intent).documents_to_delete

    async def check() -> None:
        await _access(db, actor_id)
        if datetime.now(UTC) >= draft.expires_at:
            raise CommandRejected("EXPIRED")

    await check()
    service = RAGSpaceService(db)
    await service.get_space(selected.space.id, actor_id, for_update=True)
    if await document_deletion_selection(db, actor_id, selected.request) != selected:
        raise ResourceConflictError("document_delete", detail={"error_code": "STALE_STATE"})
    await lock_document_deletion(db, actor_id, selected.request)
    await check()
    if await document_deletion_selection(db, actor_id, selected.request) != selected:
        raise ResourceConflictError("document_delete", detail={"error_code": "STALE_STATE"})
    await service.delete_selected_document_rows(
        selected.space.id, selected.request.document_ids, actor_id
    )
    await db.flush()
    await _verify_deleted_documents(db, selected)
    await check()
    try:
        await db.commit()
    except (Exception, asyncio.CancelledError) as error:
        raise CommandRejected("COMPLETION_UNKNOWN") from error
    receipt.committed = True
    public = {**selected.public_scope(after=True), "removed": True, "file_cleanup_pending": True}
    receipt.values = {"documents_to_delete": public}
    public["file_cleanup_pending"] = not await _cleanup(actor_id, selected)
