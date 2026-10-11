"""Exact row deletion commits before identity-checked physical cleanup and metrics."""

import asyncio
from datetime import UTC, datetime
from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from src.domains.agents.application.action_preparation import build_action_content
from src.domains.agents.application.asset_delete_files import cleanup_asset_file
from src.domains.agents.application.asset_delete_schemas import (
    AssetDeleteInput,
    AssetDeletePatch,
    AssetDeleteSelection,
    canonical_asset_deletion,
)
from src.domains.agents.application.asset_delete_scope import asset_deletion_selection
from src.domains.agents.application.asset_delete_spec import ASSET_DELETE_OPERATION
from src.domains.agents.application.authorization import authorize_actor, load_actor
from src.domains.agents.application.availability import require_application_tools
from src.domains.agents.application.command_service import CommandRejected
from src.domains.agents.application.draft_models import ApplicationActionDraftContent
from src.domains.attachments.models import Attachment
from src.domains.attachments.service import AttachmentService
from src.domains.users.preference_cas import PreferenceWriteReceipt
from src.domains.users.repository import UserRepository
from src.infrastructure.observability.logging import get_logger
from src.infrastructure.observability.metrics_attachments import (
    DELETION_REASON_USER,
    attachments_cleanup_deleted_total,
)

logger = get_logger(__name__)


async def _access(db: AsyncSession, actor_id: UUID) -> None:
    await require_application_tools(db)
    await load_actor(db, actor_id)


async def prepare_asset_deletion(
    db: AsyncSession, actor_id: UUID, request: AssetDeleteInput, *, command_id: UUID | None = None
) -> ApplicationActionDraftContent:
    desired = AssetDeleteInput.model_validate(request.model_dump())
    await _access(db, actor_id)
    selected = await asset_deletion_selection(db, actor_id, desired)
    await _access(db, actor_id)
    return build_action_content(
        actor_id,
        ASSET_DELETE_OPERATION,
        AssetDeletePatch(assets_to_delete=selected),
        {"assets_to_delete": selected.public_scope()},
        {"assets_to_delete": selected.public_scope(after=True)},
        command_id=command_id,
    )


async def execute_asset_deletion(
    db: AsyncSession,
    actor_id: UUID,
    draft: ApplicationActionDraftContent,
    receipt: PreferenceWriteReceipt,
) -> None:
    if draft.actor_id != actor_id or draft.operation_id != ASSET_DELETE_OPERATION.operation_id:
        raise CommandRejected("FORBIDDEN")
    if not canonical_asset_deletion(draft):
        raise CommandRejected("INVALID_INPUT")
    selected = AssetDeletePatch.model_validate(draft.intent).assets_to_delete

    async def check() -> None:
        await _access(db, actor_id)
        if datetime.now(UTC) >= draft.expires_at:
            raise CommandRejected("EXPIRED")

    await check()
    authorize_actor(await UserRepository(db).get_by_id_for_preference_update(actor_id))
    if await asset_deletion_selection(db, actor_id, selected.request, lock=True) != selected:
        raise CommandRejected("STALE_STATE")
    await check()
    updated, skipped = await AttachmentService(db).delete_generated_batch(
        actor_id, list(selected.request.ids), commit=False
    )
    if (
        skipped
        or updated != list(selected.request.ids)
        or await db.scalar(
            select(func.count(Attachment.id)).where(Attachment.id.in_(selected.request.ids))
        )
    ):
        raise CommandRejected("STALE_STATE")
    await check()
    try:
        await db.commit()
    except (Exception, asyncio.CancelledError) as error:
        raise CommandRejected("COMPLETION_UNKNOWN") from error
    receipt.committed = True
    public = {**selected.public_scope(after=True), "file_cleanup_pending": True}
    receipt.values = {"assets_to_delete": public}
    public["file_cleanup_pending"] = not await _cleanup(actor_id, selected)


async def _cleanup(actor_id: UUID, selected: AssetDeleteSelection) -> bool:
    complete = True
    for file in selected.files:
        try:
            cleaned = await cleanup_asset_file(actor_id, file)
        except (Exception, asyncio.CancelledError) as error:
            logger.warning("generated_file_cleanup_pending", error_type=type(error).__name__)
            cleaned = False
        complete = complete and cleaned
    try:
        attachments_cleanup_deleted_total.labels(reason=DELETION_REASON_USER).inc(
            len(selected.items)
        )
    except Exception as error:
        logger.warning("generated_deletion_telemetry_failed", error_type=type(error).__name__)
    return complete
