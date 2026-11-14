"""Retain every account runtime and file intent until explicit cleanup succeeds."""

import asyncio
from datetime import UTC, datetime
from uuid import UUID, uuid4

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncConnection, AsyncSession, async_sessionmaker

from src.core.attachment_lifecycle import AttachmentStatus
from src.core.config import settings
from src.core.constants import CONVERSATION_CLEANUP_PAGE_SIZE
from src.core.conversation_execution import ExecutionPhase
from src.core.exceptions import ResourceConflictError
from src.core.i18n_api_messages import APIMessages
from src.domains.conversations.cleanup_contracts import CleanupState, ConversationAction
from src.domains.conversations.cleanup_models import ConversationOperation
from src.domains.conversations.execution_models import ConversationExecution
from src.domains.conversations.models import Conversation
from src.domains.conversations.reservation_repository import ConversationReservationRepository
from src.domains.users.account_cleanup_port import account_cleanup
from src.domains.users.file_writer_models import AccountFileWriter
from src.domains.users.models import User
from src.infrastructure.database.session import Base
from src.infrastructure.observability.metrics_attachments import DELETION_REASON_USER


def cleanup_pending() -> ResourceConflictError:
    """An incomplete erasure is recoverable, never reported as completed."""
    return ResourceConflictError(
        resource_type="user",
        detail={
            "error": "account_cleanup_pending",
            "message": APIMessages.account_cleanup_pending(),
        },
    )


async def refuse_account_writers(db: AsyncSession, owner: UUID) -> None:
    """A caller holds the inactive account row; unknown producers require recovery."""
    inactive = await db.scalar(select(User.id).where(User.id == owner, User.is_active.is_(False)))
    if inactive is not None:
        reservations = ConversationReservationRepository(db)
        voice = await reservations.active_admission(owner)
        if voice is not None:
            await reservations.retire_idle(voice)
    execution = await db.scalar(
        select(ConversationExecution.id)
        .where(
            ConversationExecution.user_id == owner,
            ConversationExecution.phase != ExecutionPhase.CLOSED,
        )
        .limit(1)
    )
    files = Base.metadata.tables["attachments"]
    uploader = await db.scalar(
        select(files.c.id)
        .where(
            files.c.user_id == owner,
            files.c.status == AttachmentStatus.UPLOADED,
        )
        .limit(1)
    )
    writer = await db.scalar(
        select(AccountFileWriter.id)
        .where(
            AccountFileWriter.user_id == owner,
        )
        .limit(1)
    )
    if execution is not None or uploader is not None or writer is not None:
        raise cleanup_pending()


async def stage_account_cleanup(db: AsyncSession, user: User) -> None:
    """Stage all current runtimes and files atomically under the account's row lock.

    The caller commits before native I/O. An inactive owner admits no new writer;
    deletion_started_at additionally prevents reactivation while cleanup runs.
    Already retired runtimes retain their original operation and phase.
    """
    account_cleanup()  # Refuse missing composition before retiring any source.
    await refuse_account_writers(db, user.id)
    user.deletion_started_at = user.deletion_started_at or datetime.now(UTC)
    while True:
        rows = list(
            await db.scalars(
                select(Conversation)
                .where(
                    Conversation.user_id == user.id,
                    Conversation.deleted_at.is_(None),
                )
                .order_by(Conversation.id)
                .limit(CONVERSATION_CLEANUP_PAGE_SIZE)
                .with_for_update()
            )
        )
        if not rows:
            break
        for row in rows:
            db.add(
                ConversationOperation(
                    user_id=user.id,
                    request_id=uuid4(),
                    conversation_id=row.id,
                    action=ConversationAction.DELETE,
                    conversation_kind=row.kind,
                    old_revision=row.revision,
                    runtime_id=row.runtime_id,
                    new_revision=None,
                    attachment_ids=[],
                    previous_message_count=row.message_count,
                )
            )
            row.deleted_at = datetime.now(UTC)
        await db.flush()
    # File rows themselves are the durable intent, including files with no chat.
    # Never erase or overwrite an existing removal claim or confirmed witness.
    files = Base.metadata.tables["attachments"]
    await db.execute(
        update(files)
        .where(
            files.c.user_id == user.id,
            files.c.status.in_((AttachmentStatus.READY, AttachmentStatus.EXPIRED)),
        )
        .values(status=AttachmentStatus.DELETING, deletion_reason=DELETION_REASON_USER)
    )
    await db.flush()


async def require_account_cleanup_complete(db: AsyncSession, owner: UUID) -> None:
    """Protect every final purge from deleting the last durable cleanup intent."""
    await refuse_account_writers(db, owner)
    operation = await db.scalar(
        select(ConversationOperation.id)
        .where(
            ConversationOperation.user_id == owner,
            ConversationOperation.state != CleanupState.SUCCEEDED,
        )
        .limit(1)
    )
    files = Base.metadata.tables["attachments"]
    file_id = await db.scalar(select(files.c.id).where(files.c.user_id == owner).limit(1))
    if operation is not None or file_id is not None:
        raise cleanup_pending()


async def clean_account_runtime_page(db: AsyncSession, owner: UUID) -> int:
    """No transaction spans an external wait, and cancellation joins owned work."""
    bind = db.bind.engine if isinstance(db.bind, AsyncConnection) else db.bind
    sessions = async_sessionmaker(bind, expire_on_commit=False)
    try:
        async with asyncio.timeout(settings.account_cleanup_wait_seconds):
            removed = await account_cleanup().cleanup_page(sessions, owner)
    except TimeoutError as exc:
        raise cleanup_pending() from exc
    try:
        await require_account_cleanup_complete(db, owner)
    finally:
        await db.commit()
    return removed
