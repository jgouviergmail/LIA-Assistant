"""Exact native approval commits the owned claim before launching fenced Source work."""

import asyncio
from datetime import UTC, datetime
from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.config import settings
from src.core.constants import RAG_DRIVE_MAX_FILES_PER_SYNC
from src.core.exceptions import AuthorizationError
from src.domains.agents.application.action_preparation import build_action_content
from src.domains.agents.application.authorization import load_actor
from src.domains.agents.application.availability import require_application_tools
from src.domains.agents.application.command_service import CommandRejected
from src.domains.agents.application.draft_models import ApplicationActionDraftContent
from src.domains.agents.application.source_sync_schemas import (
    SourceSyncInput,
    SourceSyncPatch,
    SourceSyncSelection,
    canonical_source_sync,
)
from src.domains.agents.application.source_sync_spec import SOURCE_SYNC_OPERATION
from src.domains.agents.application.source_unlink_schemas import SourceUnlinkInput
from src.domains.agents.application.source_unlink_scope import source_unlink_selection
from src.domains.feature_switches.guard import require_capability_fresh
from src.domains.feature_switches.registry import PlatformCapability
from src.domains.rag_spaces.drive_sync import RAGDriveSyncService
from src.domains.rag_spaces.mail_source_service import RAGMailSyncService
from src.domains.rag_spaces.models import (
    RAGDocument,
    RAGDocumentStatus,
    RAGDriveSource,
    RAGMailSource,
)
from src.domains.rag_spaces.service import RAGSpaceService
from src.domains.rag_spaces.source_worker_lease import (
    SourceLeaseLost,
    SourceWorkerLease,
    native_source_worker_id,
    require_source_worker,
    source_worker_scope,
)
from src.domains.rag_spaces.source_worker_runtime import run_native_source_worker
from src.domains.users.preference_cas import PreferenceWriteReceipt
from src.infrastructure.async_utils import safe_fire_and_forget


async def _access(db: AsyncSession, actor_id: UUID, request: SourceSyncInput) -> None:
    await require_application_tools(db)
    await require_capability_fresh(db, PlatformCapability.RAG_SPACES)
    await load_actor(db, actor_id)
    if not (
        settings.rag_spaces_drive_sync_enabled
        if request.kind == "drive"
        else settings.rag_spaces_mail_sync_enabled
    ):
        raise AuthorizationError(detail={"error_code": "CAPABILITY_DISABLED"})


async def _selection(
    db: AsyncSession, actor_id: UUID, request: SourceSyncInput, *, lock: bool = False
) -> SourceSyncSelection:
    source = await source_unlink_selection(
        db, actor_id, SourceUnlinkInput.model_validate(request.model_dump()), lock=lock
    )
    reference = (
        RAGDocument.drive_source_id if request.kind == "drive" else RAGDocument.mail_source_id
    )
    active = await db.scalar(
        select(func.count(RAGDocument.id)).where(
            reference == request.source_id,
            RAGDocument.status.in_(
                (
                    RAGDocumentStatus.PENDING,
                    RAGDocumentStatus.PROCESSING,
                    RAGDocumentStatus.REINDEXING,
                )
            ),
        )
    )
    if active:
        raise CommandRejected("CONSTRAINT_VIOLATION")
    model = RAGDriveSource if request.kind == "drive" else RAGMailSource
    provider = RAGDriveSource.folder_id if request.kind == "drive" else RAGMailSource.label_id
    provider_id = await db.scalar(
        select(provider).where(
            model.id == request.source_id,
            model.user_id == actor_id,
            model.space_id == request.space_id,
        )
    )
    if not isinstance(provider_id, str):
        raise CommandRejected("INVALID_RESPONSE_FORMAT")
    return SourceSyncSelection(
        source=source,
        max_documents=settings.rag_spaces_max_docs_per_space,
        provider_id=provider_id,
        max_file_bytes=settings.rag_spaces_max_file_size_mb * 1024 * 1024,
        max_chunks=settings.rag_spaces_max_chunks_per_document,
        max_items=(
            RAG_DRIVE_MAX_FILES_PER_SYNC
            if request.kind == "drive"
            else settings.rag_mail_max_threads_per_sync
        ),
    )


async def prepare_source_sync(
    db: AsyncSession, actor_id: UUID, request: SourceSyncInput, *, command_id: UUID | None = None
) -> ApplicationActionDraftContent:
    request = SourceSyncInput.model_validate(request.model_dump())
    await _access(db, actor_id, request)
    selected = await _selection(db, actor_id, request)
    await _access(db, actor_id, request)
    return build_action_content(
        actor_id,
        SOURCE_SYNC_OPERATION,
        SourceSyncPatch(source_to_sync=selected),
        {"source_to_sync": selected.public_scope()},
        {"source_to_sync": selected.public_scope(after=True)},
        command_id=command_id,
    )


def launch_source_sync(lease: SourceWorkerLease) -> None:
    safe_fire_and_forget(
        run_native_source_worker(lease), name=f"native_source_sync_{lease.source_id}"
    )


async def execute_source_sync(
    db: AsyncSession,
    actor_id: UUID,
    draft: ApplicationActionDraftContent,
    receipt: PreferenceWriteReceipt,
) -> None:
    if draft.actor_id != actor_id or draft.operation_id != SOURCE_SYNC_OPERATION.operation_id:
        raise CommandRejected("FORBIDDEN")
    if not canonical_source_sync(draft):
        raise CommandRejected("INVALID_INPUT")
    selected = SourceSyncPatch.model_validate(draft.intent).source_to_sync
    request = SourceSyncInput.model_validate(selected.source.request.model_dump())

    async def check() -> None:
        await _access(db, actor_id, request)
        if datetime.now(UTC) >= draft.expires_at:
            raise CommandRejected("EXPIRED")

    await check()
    await RAGSpaceService(db).get_space(request.space_id, actor_id, for_update=True)
    await check()
    if await _selection(db, actor_id, request, lock=True) != selected:
        raise CommandRejected("STALE_STATE")
    worker_id = native_source_worker_id(draft.command_id)
    service = RAGDriveSyncService(db) if request.kind == "drive" else RAGMailSyncService(db)
    if not await service.try_acquire_sync_lock(
        request.source_id, commit=False, worker_id=worker_id
    ):
        raise CommandRejected("CONSTRAINT_VIOLATION")
    lease = SourceWorkerLease(
        request.kind,
        request.source_id,
        request.space_id,
        actor_id,
        worker_id,
        provider_id=selected.provider_id,
        max_documents=selected.max_documents,
        max_items=selected.max_items,
        max_file_bytes=selected.max_file_bytes,
        max_chunks=selected.max_chunks,
    )
    try:
        with source_worker_scope(lease):
            await require_source_worker(db)
    except SourceLeaseLost as error:
        raise CommandRejected("STALE_STATE") from error
    await check()
    try:
        await db.commit()
    except (Exception, asyncio.CancelledError) as error:
        raise CommandRejected("COMPLETION_UNKNOWN") from error
    receipt.committed = True
    receipt.values = {"source_to_sync": selected.public_scope(after=True)}
    launch_source_sync(lease)
