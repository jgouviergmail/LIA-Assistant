"""Confirmed retain-only Source unlink under owner, parent and source write fences."""

import asyncio
from datetime import UTC, datetime
from uuid import UUID

import structlog
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from src.domains.agents.application.action_preparation import build_action_content
from src.domains.agents.application.authorization import load_actor
from src.domains.agents.application.availability import require_application_tools
from src.domains.agents.application.command_service import CommandRejected
from src.domains.agents.application.draft_models import ApplicationActionDraftContent
from src.domains.agents.application.source_unlink_schemas import (
    SourceUnlinkInput,
    SourceUnlinkPatch,
    SourceUnlinkSelection,
    canonical_source_unlink,
)
from src.domains.agents.application.source_unlink_scope import (
    document_id_digest,
    source_unlink_selection,
)
from src.domains.agents.application.source_unlink_spec import SOURCE_UNLINK_OPERATION
from src.domains.feature_switches.guard import require_capability_fresh
from src.domains.feature_switches.registry import PlatformCapability
from src.domains.rag_spaces.drive_sync import RAGDriveSyncService
from src.domains.rag_spaces.mail_source_service import RAGMailSyncService
from src.domains.rag_spaces.models import RAGDocument, RAGDriveSource, RAGMailSource
from src.domains.rag_spaces.service import RAGSpaceService
from src.domains.users.preference_cas import PreferenceWriteReceipt
from src.infrastructure.observability.metrics_rag_spaces import (
    rag_drive_sources_total_count,
    rag_mail_sources_total_count,
)

logger = structlog.get_logger(__name__)


async def _access(db: AsyncSession, actor_id: UUID) -> None:
    await require_application_tools(db)
    await require_capability_fresh(db, PlatformCapability.RAG_SPACES)
    await load_actor(db, actor_id)


async def prepare_source_unlink(
    db: AsyncSession, actor_id: UUID, request: SourceUnlinkInput, *, command_id: UUID | None = None
) -> ApplicationActionDraftContent:
    request = SourceUnlinkInput.model_validate(request.model_dump())
    await _access(db, actor_id)
    scope = await source_unlink_selection(db, actor_id, request)
    await _access(db, actor_id)
    return build_action_content(
        actor_id,
        SOURCE_UNLINK_OPERATION,
        SourceUnlinkPatch(source_to_unlink=scope),
        {"source_to_unlink": scope.public_scope()},
        {"source_to_unlink": scope.public_scope(after=True)},
        command_id=command_id,
    )


async def execute_source_unlink(
    db: AsyncSession,
    actor_id: UUID,
    draft: ApplicationActionDraftContent,
    receipt: PreferenceWriteReceipt,
) -> None:
    if draft.actor_id != actor_id or draft.operation_id != SOURCE_UNLINK_OPERATION.operation_id:
        raise CommandRejected("FORBIDDEN")
    if not canonical_source_unlink(draft):
        raise CommandRejected("INVALID_INPUT")
    selected = SourceUnlinkPatch.model_validate(draft.intent).source_to_unlink
    request = selected.request

    async def check() -> None:
        await _access(db, actor_id)
        if datetime.now(UTC) >= draft.expires_at:
            raise CommandRejected("EXPIRED")

    await check()
    await RAGSpaceService(db).get_space(request.space_id, actor_id, for_update=True)
    await check()
    if await source_unlink_selection(db, actor_id, request, lock=True) != selected:
        raise CommandRejected("STALE_STATE")
    if request.kind == "drive":
        await RAGDriveSyncService(db).unlink_folder(
            request.space_id, request.source_id, actor_id, commit=False
        )
    else:
        await RAGMailSyncService(db).unlink_label(
            request.space_id, request.source_id, actor_id, commit=False
        )
    await _verify_source_unlink(db, selected)
    await check()
    try:
        await db.commit()
    except (Exception, asyncio.CancelledError) as error:
        raise CommandRejected("COMPLETION_UNKNOWN") from error
    receipt.committed = True
    receipt.values = {"source_to_unlink": selected.public_scope(after=True)}
    _publish_unlink_metric(request)


async def _verify_source_unlink(db: AsyncSession, selected: SourceUnlinkSelection) -> None:
    request = selected.request
    model = RAGDriveSource if request.kind == "drive" else RAGMailSource
    reference = (
        RAGDocument.drive_source_id if request.kind == "drive" else RAGDocument.mail_source_id
    )
    if await db.scalar(select(model.id).where(model.id == request.source_id)) is not None:
        raise ValueError("Source did not unlink the exact source")
    if await db.scalar(select(func.count(RAGDocument.id)).where(reference == request.source_id)):
        raise ValueError("Source did not release all document references")
    if await document_id_digest(db, request.space_id) != selected.documents_digest:
        raise ValueError("Source must retain all document identities")


def _publish_unlink_metric(request: SourceUnlinkInput) -> None:
    try:
        (
            rag_drive_sources_total_count
            if request.kind == "drive"
            else rag_mail_sources_total_count
        ).dec()
    except Exception as error:
        logger.warning("source_unlink_telemetry_failed", error_type=type(error).__name__)
