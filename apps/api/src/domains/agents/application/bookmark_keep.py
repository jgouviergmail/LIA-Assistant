"""An exact saved-answer copy commits before any indexing job is requested."""

import asyncio
from datetime import UTC, datetime
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.domains.agents.application.action_preparation import build_action_content
from src.domains.agents.application.authorization import authorize_actor, load_actor
from src.domains.agents.application.availability import require_application_tools
from src.domains.agents.application.bookmark_keep_schemas import (
    BookmarkKeepInput,
    BookmarkKeepObservation,
    BookmarkKeepPatch,
    canonical_bookmark_keep,
)
from src.domains.agents.application.bookmark_keep_scope import (
    bookmark_copy_digest,
    observe_bookmark_keep,
    resolve_bookmark_keep,
)
from src.domains.agents.application.bookmark_keep_spec import BOOKMARK_KEEP_OPERATION
from src.domains.agents.application.command_service import CommandRejected
from src.domains.agents.application.draft_models import ApplicationActionDraftContent
from src.domains.bookmarks.models import MessageBookmark
from src.domains.bookmarks.service import BookmarkService, enqueue_bookmark_index
from src.domains.conversations.models import Conversation
from src.domains.feature_switches.guard import require_capability_fresh
from src.domains.feature_switches.registry import PlatformCapability
from src.domains.users.preference_cas import PreferenceWriteReceipt
from src.domains.users.repository import UserRepository
from src.infrastructure.observability.logging import get_logger

logger = get_logger(__name__)


async def _access(db: AsyncSession, actor_id: UUID) -> None:
    await require_application_tools(db)
    await load_actor(db, actor_id)
    await require_capability_fresh(db, PlatformCapability.BOOKMARKS)


async def prepare_bookmark_keep(
    db: AsyncSession, actor_id: UUID, request: BookmarkKeepInput, *, command_id: UUID | None = None
) -> ApplicationActionDraftContent:
    desired = BookmarkKeepInput.model_validate(request.model_dump())
    await _access(db, actor_id)
    resolved = await resolve_bookmark_keep(db, actor_id, desired)
    selected = await observe_bookmark_keep(db, actor_id, resolved)
    await _access(db, actor_id)
    return build_action_content(
        actor_id,
        BOOKMARK_KEEP_OPERATION,
        BookmarkKeepPatch(saved_answer_to_keep=selected),
        {"saved_answer_to_keep": selected.public_scope()},
        {"saved_answer_to_keep": selected.public_scope(after=True)},
        command_id=command_id,
    )


async def execute_bookmark_keep(
    db: AsyncSession,
    actor_id: UUID,
    draft: ApplicationActionDraftContent,
    receipt: PreferenceWriteReceipt,
) -> None:
    if draft.actor_id != actor_id or draft.operation_id != BOOKMARK_KEEP_OPERATION.operation_id:
        raise CommandRejected("FORBIDDEN")
    if not canonical_bookmark_keep(draft):
        raise CommandRejected("INVALID_INPUT")
    selected = BookmarkKeepPatch.model_validate(draft.intent).saved_answer_to_keep

    async def check() -> None:
        await _access(db, actor_id)
        if datetime.now(UTC) >= draft.expires_at:
            raise CommandRejected("EXPIRED")

    await check()
    service = BookmarkService(db)
    await service.repository.lock_keep_owner(actor_id)
    authorize_actor(await UserRepository(db).get_by_id_for_preference_update(actor_id))
    await _lock_copy_source(db, actor_id, service, selected)
    if await observe_bookmark_keep(db, actor_id, selected.request) != selected:
        raise CommandRejected("STALE_STATE")
    row, created = await service.keep(actor_id, selected.request.message_id, commit=False)
    if bookmark_copy_digest(row) != selected.copy_digest or created != (
        selected.existing_id is None
    ):
        raise CommandRejected("STALE_STATE")
    expected = selected.kept_count + int(created)
    if await service.repository.count_for_user(actor_id) != expected:
        raise CommandRejected("STALE_STATE")
    await check()
    identity = row.id
    try:
        await db.commit()
    except (Exception, asyncio.CancelledError) as error:
        raise CommandRejected("COMPLETION_UNKNOWN") from error
    receipt.committed, receipt.no_op = True, not created
    receipt.values = {
        "saved_answer_to_keep": {
            **selected.public_scope(after=True),
            "bookmark_id": str(identity),
            "indexing_pending": created,
        }
    }
    if created:
        try:
            enqueue_bookmark_index(identity)
        except Exception as error:
            logger.warning("bookmark_index_enqueue_pending", error_type=type(error).__name__)


async def _lock_copy_source(
    db: AsyncSession, actor_id: UUID, service: BookmarkService, selected: BookmarkKeepObservation
) -> None:
    """Keep scope/message locks in the same order for every exact copy."""
    if selected.existing_id is not None:
        await db.execute(
            select(MessageBookmark.id)
            .where(MessageBookmark.id == selected.existing_id, MessageBookmark.user_id == actor_id)
            .with_for_update()
        )
    else:
        if (
            await db.scalar(
                select(Conversation.id)
                .where(
                    Conversation.id == selected.conversation_id, Conversation.user_id == actor_id
                )
                .with_for_update()
            )
            is None
        ):
            raise CommandRejected("NOT_FOUND_OR_UNAUTHORIZED")
        message = await service.repository.owned_assistant_message(
            actor_id, selected.request.message_id, lock=True
        )
        if message is None:
            raise CommandRejected("NOT_FOUND_OR_UNAUTHORIZED")
        await service.repository.preceding_user_message(message, lock=True)
