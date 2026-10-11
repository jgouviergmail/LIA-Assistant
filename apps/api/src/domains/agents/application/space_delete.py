"""Confirmed source deletion, exact cascade checks, and cleanup only after commit acknowledgement."""

import asyncio
from datetime import UTC, datetime
from uuid import UUID

import structlog
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.exceptions import ResourceConflictError
from src.domains.agents.application.action_preparation import build_action_content
from src.domains.agents.application.authorization import load_actor
from src.domains.agents.application.availability import require_application_tools
from src.domains.agents.application.command_service import CommandRejected
from src.domains.agents.application.draft_models import ApplicationActionDraftContent
from src.domains.agents.application.space_delete_schemas import (
    SpaceDeleteInput,
    SpaceDeletePatch,
    SpaceDeleteSelection,
    canonical_space_deletion,
)
from src.domains.agents.application.space_delete_scope import (
    deletion_selection,
    lock_deletion_children,
)
from src.domains.agents.application.space_delete_spec import SPACE_DELETE_OPERATION
from src.domains.feature_switches.guard import require_capability_fresh
from src.domains.feature_switches.registry import PlatformCapability
from src.domains.rag_spaces import space_deletion
from src.domains.rag_spaces.models import (
    RAGChunk,
    RAGDocument,
    RAGDriveSource,
    RAGMailSource,
    RAGSpace,
)
from src.domains.rag_spaces.service import RAGSpaceService
from src.domains.users.preference_cas import PreferenceWriteReceipt

logger = structlog.get_logger(__name__)


async def _access(db: AsyncSession, actor_id: UUID) -> None:
    await require_application_tools(db)
    await require_capability_fresh(db, PlatformCapability.RAG_SPACES)
    await load_actor(db, actor_id)


async def prepare_space_deletion(
    db: AsyncSession, actor_id: UUID, request: SpaceDeleteInput, *, command_id: UUID | None = None
) -> ApplicationActionDraftContent:
    selected = SpaceDeleteInput.model_validate(request.model_dump())
    await _access(db, actor_id)
    scope = await deletion_selection(db, actor_id, selected)
    await _access(db, actor_id)
    return build_action_content(
        actor_id,
        SPACE_DELETE_OPERATION,
        SpaceDeletePatch(space_delete=scope),
        {"space_delete": scope.public_scope()},
        {"space_delete": scope.public_scope(after=True)},
        command_id=command_id,
    )


async def _verify_deletion(
    db: AsyncSession, actor_id: UUID, expected: SpaceDeleteSelection
) -> None:
    if await db.scalar(select(func.count(RAGSpace.id)).where(RAGSpace.id == expected.space.id)):
        raise ValueError("Source space removal was not persisted")
    for model in (RAGDocument, RAGDriveSource, RAGMailSource, RAGChunk):
        if await db.scalar(select(func.count(model.id)).where(model.space_id == expected.space.id)):
            raise ValueError("Source deletion must remove the exact approved children")
    owned = int(
        await db.scalar(select(func.count(RAGSpace.id)).where(RAGSpace.user_id == actor_id)) or 0
    )
    if owned != expected.owned_spaces - 1:
        raise ValueError("Source deletion changed an unapproved owned space")


async def _publish_cleanup(actor_id: UUID, expected: SpaceDeleteSelection) -> bool:
    try:
        cleaned = await space_deletion.cleanup_space_files(actor_id, expected.space.id)
    except (Exception, asyncio.CancelledError) as exc:
        # The deletion already has an ACK. Close its books truthfully even
        # when cleanup is interrupted, without repeating the database write.
        logger.warning("space_file_cleanup_pending", error_type=type(exc).__name__)
        cleaned = False
    try:
        space_deletion.publish_space_deletion(
            expected.space.is_active, tuple(doc.status for doc in expected.items)
        )
    except Exception as exc:
        logger.warning("space_deletion_telemetry_failed", error_type=type(exc).__name__)
    return cleaned


async def execute_space_deletion(
    db: AsyncSession,
    actor_id: UUID,
    draft: ApplicationActionDraftContent,
    receipt: PreferenceWriteReceipt,
) -> None:
    if draft.actor_id != actor_id or draft.operation_id != SPACE_DELETE_OPERATION.operation_id:
        raise CommandRejected("FORBIDDEN")
    if not canonical_space_deletion(draft):
        raise ValueError("Space deletion requires exact canonical consent")
    expected = SpaceDeletePatch.model_validate(draft.intent).space_delete

    async def check() -> None:
        await _access(db, actor_id)
        if datetime.now(UTC) >= draft.expires_at:
            raise CommandRejected("EXPIRED")

    await check()
    service = RAGSpaceService(db)
    await service.get_space(expected.space.id, actor_id, for_update=True)
    # Check active jobs before locks to avoid waiting while holding their parent.
    if await deletion_selection(db, actor_id, expected.request) != expected:
        raise ResourceConflictError("space_delete", detail={"error_code": "STALE_STATE"})
    await lock_deletion_children(db, expected.space.id)
    await check()
    if await deletion_selection(db, actor_id, expected.request) != expected:
        raise ResourceConflictError("space_delete", detail={"error_code": "STALE_STATE"})
    await service.delete_space(expected.space.id, actor_id, commit=False)
    await db.flush()
    await _verify_deletion(db, actor_id, expected)
    await check()
    try:
        await db.commit()
    except (Exception, asyncio.CancelledError) as exc:
        raise CommandRejected("COMPLETION_UNKNOWN") from exc
    receipt.committed = True
    public = {**expected.public_scope(after=True), "removed": True, "file_cleanup_pending": True}
    receipt.values = {"space_delete": public}
    public["file_cleanup_pending"] = not await _publish_cleanup(actor_id, expected)
