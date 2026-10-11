"""A single known commit removes exact source rows before any physical cleanup."""

import asyncio
from datetime import UTC, datetime
from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from src.domains.agents.application.action_preparation import build_action_content
from src.domains.agents.application.command_service import CommandRejected
from src.domains.agents.application.document_delete import _cleanup
from src.domains.agents.application.document_delete_scope import lock_document_deletion
from src.domains.agents.application.draft_models import ApplicationActionDraftContent
from src.domains.agents.application.source_delete_schemas import (
    SourceDeleteInput,
    SourceDeletePatch,
    SourceDeleteSelection,
    canonical_source_deletion,
)
from src.domains.agents.application.source_delete_scope import source_deletion_selection
from src.domains.agents.application.source_delete_spec import SOURCE_DELETE_OPERATION
from src.domains.agents.application.source_unlink import _access
from src.domains.rag_spaces.drive_sync import RAGDriveSyncService
from src.domains.rag_spaces.mail_source_service import RAGMailSyncService
from src.domains.rag_spaces.models import RAGChunk, RAGDocument, RAGDriveSource, RAGMailSource
from src.domains.rag_spaces.service import RAGSpaceService
from src.domains.users.preference_cas import PreferenceWriteReceipt
from src.infrastructure.observability.logging import get_logger
from src.infrastructure.observability.metrics_rag_spaces import (
    rag_drive_sources_total_count,
    rag_mail_sources_total_count,
)

logger = get_logger(__name__)


async def prepare_source_deletion(
    db: AsyncSession, actor_id: UUID, request: SourceDeleteInput, *, command_id: UUID | None = None
) -> ApplicationActionDraftContent:
    request = SourceDeleteInput.model_validate(request.model_dump())
    await _access(db, actor_id)
    selected = await source_deletion_selection(db, actor_id, request)
    await _access(db, actor_id)
    return build_action_content(
        actor_id,
        SOURCE_DELETE_OPERATION,
        SourceDeletePatch(source_to_delete=selected),
        {"source_to_delete": selected.public_scope()},
        {"source_to_delete": selected.public_scope(after=True)},
        command_id=command_id,
    )


async def execute_source_deletion(
    db: AsyncSession,
    actor_id: UUID,
    draft: ApplicationActionDraftContent,
    receipt: PreferenceWriteReceipt,
) -> None:
    if draft.actor_id != actor_id or draft.operation_id != SOURCE_DELETE_OPERATION.operation_id:
        raise CommandRejected("FORBIDDEN")
    if not canonical_source_deletion(draft):
        raise CommandRejected("INVALID_INPUT")
    selected = SourceDeletePatch.model_validate(draft.intent).source_to_delete
    request = SourceDeleteInput.model_validate(selected.source.request.model_dump())

    async def check() -> None:
        await _access(db, actor_id)
        if datetime.now(UTC) >= draft.expires_at:
            raise CommandRejected("EXPIRED")

    await check()
    service = RAGSpaceService(db)
    await service.get_space(request.space_id, actor_id, for_update=True)
    if await source_deletion_selection(db, actor_id, request, lock=True) != selected:
        raise CommandRejected("STALE_STATE")
    for batch in selected.batches:
        await lock_document_deletion(db, actor_id, batch.request)
    await check()
    if await source_deletion_selection(db, actor_id, request, lock=True) != selected:
        raise CommandRejected("STALE_STATE")
    for batch in selected.batches:
        await service.delete_selected_document_rows(
            request.space_id, batch.request.document_ids, actor_id
        )
    if request.kind == "drive":
        await RAGDriveSyncService(db).unlink_folder(
            request.space_id, request.source_id, actor_id, commit=False
        )
    else:
        await RAGMailSyncService(db).unlink_label(
            request.space_id, request.source_id, actor_id, commit=False
        )
    await _verify_source_deletion(db, selected)
    await check()
    try:
        await db.commit()
    except (Exception, asyncio.CancelledError) as error:
        raise CommandRejected("COMPLETION_UNKNOWN") from error
    receipt.committed = True
    public = {**selected.public_scope(after=True), "file_cleanup_pending": True}
    receipt.values = {"source_to_delete": public}
    public["file_cleanup_pending"] = not await _publish_cleanup(actor_id, selected)


async def _verify_source_deletion(db: AsyncSession, selected: SourceDeleteSelection) -> None:
    request = selected.source.request
    model = RAGDriveSource if request.kind == "drive" else RAGMailSource
    if await db.scalar(select(model.id).where(model.id == request.source_id)) is not None:
        raise CommandRejected("STALE_STATE")
    for batch in selected.batches:
        if await db.scalar(
            select(func.count(RAGDocument.id)).where(RAGDocument.id.in_(batch.request.document_ids))
        ) or await db.scalar(
            select(func.count(RAGChunk.id)).where(
                RAGChunk.document_id.in_(batch.request.document_ids)
            )
        ):
            raise CommandRejected("STALE_STATE")
    if selected.batches:
        total = await db.scalar(
            select(func.count(RAGDocument.id)).where(RAGDocument.space_id == request.space_id)
        )
        if total != selected.batches[0].space_documents - selected.source.documents:
            raise CommandRejected("STALE_STATE")


async def _publish_cleanup(actor_id: UUID, selected: SourceDeleteSelection) -> bool:
    complete = True
    for batch in selected.batches:
        complete = await _cleanup(actor_id, batch) and complete
    try:
        (
            rag_drive_sources_total_count
            if selected.source.request.kind == "drive"
            else rag_mail_sources_total_count
        ).dec()
    except Exception as error:
        logger.warning("source_deletion_telemetry_failed", error_type=type(error).__name__)
    return complete
