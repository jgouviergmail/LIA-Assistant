"""Exact native movement stages exclusive copies, moves rows atomically, then cleans originals."""

import asyncio
from collections.abc import Awaitable, Callable
from datetime import UTC, datetime
from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.exceptions import ResourceConflictError
from src.domains.agents.application.action_preparation import build_action_content
from src.domains.agents.application.command_service import CommandRejected
from src.domains.agents.application.document_delete_scope import (
    _private_digest,
    document_deletion_selection,
    lock_document_deletion,
)
from src.domains.agents.application.document_move_schemas import (
    DocumentMoveInput,
    DocumentMovePatch,
    DocumentMoveSelection,
    canonical_document_move,
)
from src.domains.agents.application.document_move_scope import (
    document_move_selection,
    require_move_idle,
)
from src.domains.agents.application.document_move_spec import DOCUMENT_MOVE_OPERATION
from src.domains.agents.application.draft_models import ApplicationActionDraftContent
from src.domains.agents.application.space_delete import _access
from src.domains.agents.application.space_update import _source_row
from src.domains.agents.effects.digest import payload_digest
from src.domains.rag_spaces.document_deletion_cleanup import cleanup_deleted_document_file
from src.domains.rag_spaces.document_move_files import (
    StagedDocumentFile,
    rollback_staged_file,
    stage_document_file,
)
from src.domains.rag_spaces.document_ops import relocate_document_rows
from src.domains.rag_spaces.models import RAGDocument
from src.domains.rag_spaces.service import RAGSpaceService
from src.domains.users.preference_cas import PreferenceWriteReceipt
from src.infrastructure.observability.logging import get_logger

logger = get_logger(__name__)
Check = Callable[[], Awaitable[None]]


async def prepare_document_move(
    db: AsyncSession, actor_id: UUID, request: DocumentMoveInput, *, command_id: UUID | None = None
) -> ApplicationActionDraftContent:
    request = DocumentMoveInput.model_validate(request.model_dump())
    await _access(db, actor_id)
    selected = await document_move_selection(db, actor_id, request)
    await _access(db, actor_id)
    return build_action_content(
        actor_id,
        DOCUMENT_MOVE_OPERATION,
        DocumentMovePatch(documents_to_move=selected),
        {"documents_to_move": selected.public_scope()},
        {"documents_to_move": selected.public_scope(after=True)},
        command_id=command_id,
    )


async def _count(db: AsyncSession, space_id: UUID) -> int:
    return int(
        await db.scalar(select(func.count(RAGDocument.id)).where(RAGDocument.space_id == space_id))
        or 0
    )


async def _verify_parents(
    db: AsyncSession, actor_id: UUID, selected: DocumentMoveSelection, *, after: bool = False
) -> None:
    moved = len(selected.request.document_ids) if after else 0
    if (
        payload_digest(await _source_row(db, actor_id, selected.request.space_id))
        != selected.source_digest
        or payload_digest(await _source_row(db, actor_id, selected.target.id))
        != selected.target_digest
        or await _count(db, selected.request.space_id) != selected.documents.space_documents - moved
        or await _count(db, selected.target.id) != selected.target_documents + moved
    ):
        raise ResourceConflictError("document_move", detail={"error_code": "STALE_STATE"})


async def _rollback_copies(staged: list[StagedDocumentFile]) -> None:
    for file in staged:
        try:
            if not await rollback_staged_file(file):
                logger.warning("document_move_staging_cleanup_pending")
        except (Exception, asyncio.CancelledError) as error:
            logger.warning("document_move_staging_cleanup_pending", error_type=type(error).__name__)


async def _clean_originals(actor_id: UUID, selected: DocumentMoveSelection) -> bool:
    complete = True
    for file in selected.documents.files:
        try:
            cleaned = await cleanup_deleted_document_file(
                actor_id, selected.request.space_id, file.stored_filename, file.file_digest
            )
        except (Exception, asyncio.CancelledError) as error:
            logger.warning(
                "document_move_original_cleanup_pending", error_type=type(error).__name__
            )
            cleaned = False
        complete = complete and cleaned
    return complete


async def _stage_sources(
    actor_id: UUID, selected: DocumentMoveSelection, staged: list[StagedDocumentFile], check: Check
) -> None:
    for item, file in zip(selected.documents.items, selected.documents.files, strict=True):
        await check()
        copy = await stage_document_file(
            actor_id,
            selected.request.space_id,
            selected.target.id,
            file.stored_filename,
            file.file_digest,
            item.file_size,
        )
        if copy is not None:
            staged.append(copy)


async def _move_index_rows(
    db: AsyncSession, actor_id: UUID, selected: DocumentMoveSelection
) -> None:
    documents = list(
        (
            await db.scalars(
                select(RAGDocument).where(RAGDocument.id.in_(selected.request.document_ids))
            )
        ).all()
    )
    service = RAGSpaceService(db)
    for document in documents:
        await relocate_document_rows(service, document, selected.target.id, commit=False)
    await _verify_parents(db, actor_id, selected, after=True)
    if (
        await _private_digest(db, selected.request.document_ids, ignore_updated_at=True)
        != selected.result_digest
    ):
        raise ResourceConflictError("document_move", detail={"error_code": "STALE_STATE"})


async def execute_document_move(
    db: AsyncSession,
    actor_id: UUID,
    draft: ApplicationActionDraftContent,
    receipt: PreferenceWriteReceipt,
) -> None:
    if draft.actor_id != actor_id or draft.operation_id != DOCUMENT_MOVE_OPERATION.operation_id:
        raise CommandRejected("FORBIDDEN")
    if not canonical_document_move(draft):
        raise ValueError("Movement requires canonical exact approval")
    selected = DocumentMovePatch.model_validate(draft.intent).documents_to_move

    async def check() -> None:
        await _access(db, actor_id)
        await require_move_idle()
        if datetime.now(UTC) >= draft.expires_at:
            raise CommandRejected("EXPIRED")

    await check()
    service = RAGSpaceService(db)
    for space_id in sorted((selected.request.space_id, selected.target.id)):
        await service.get_space(space_id, actor_id, for_update=True)
    if await document_move_selection(db, actor_id, selected.request) != selected:
        raise ResourceConflictError("document_move", detail={"error_code": "STALE_STATE"})
    await lock_document_deletion(db, actor_id, selected.documents.request)
    if await document_move_selection(db, actor_id, selected.request) != selected:
        raise ResourceConflictError("document_move", detail={"error_code": "STALE_STATE"})
    staged: list[StagedDocumentFile] = []
    committing = False
    try:
        await _stage_sources(actor_id, selected, staged, check)
        await check()
        await _verify_parents(db, actor_id, selected)
        if (
            await document_deletion_selection(db, actor_id, selected.documents.request)
            != selected.documents
        ):
            raise ResourceConflictError("document_move", detail={"error_code": "STALE_STATE"})
        await _move_index_rows(db, actor_id, selected)
        await check()
        committing = True
        try:
            await db.commit()
        except (Exception, asyncio.CancelledError) as error:
            raise CommandRejected("COMPLETION_UNKNOWN") from error
    except BaseException:
        if not committing:
            await db.rollback()
            await _rollback_copies(staged)
        raise
    receipt.committed = True
    public = {**selected.public_scope(after=True), "moved": True, "file_cleanup_pending": True}
    receipt.values = {"documents_to_move": public}
    public["file_cleanup_pending"] = not await _clean_originals(actor_id, selected)
