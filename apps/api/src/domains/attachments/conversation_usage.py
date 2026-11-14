"""Atomic accepted file uses and last-use retirement within a caller's transaction."""

from datetime import UTC, datetime
from uuid import UUID

from sqlalchemy import delete, exists, or_, select, update
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.conversation_target import ConversationRef
from src.core.exceptions import ResourceNotFoundError
from src.core.repository import BaseRepository
from src.domains.attachments.models import (
    Attachment,
    AttachmentOrigin,
    AttachmentStatus,
    ConversationAttachmentUsage,
)
from src.domains.users.conversation_authority import hold_conversation_source
from src.infrastructure.observability.metrics_attachments import DELETION_REASON_CONVERSATION_RESET


class ConversationAttachmentUsageRepository(BaseRepository[ConversationAttachmentUsage]):
    """Serialize acceptance/removal on each file, with no commit or physical I/O."""

    def __init__(self, db: AsyncSession) -> None:
        """Use the caller's source-publication or lifecycle transaction."""
        super().__init__(db, ConversationAttachmentUsage)

    async def accept_batch(
        self, owner_id: UUID, attachment_ids: list[UUID], target: ConversationRef
    ) -> list[Attachment]:
        """Validate ALL files and idempotently record their current discussion use.

        Args:
            owner_id: Authenticated owner; cannot be replaced by the supplied target.
            attachment_ids: Requested files, with repetitions treated as one use.
            target: The immutable discussion that accepted them.

        Returns:
            Accepted files, without extending any deadline or changing provenance.

        Raises:
            ExecutionRevoked: The account or discussion generation was retired.
            ResourceNotFoundError: Any file is missing, foreign, expired or retiring.
        """
        await hold_conversation_source(self.db, owner_id, target)
        wanted = set(attachment_ids)
        if not wanted:
            return []
        rows = list(
            await self.db.scalars(
                select(Attachment)
                .where(
                    Attachment.id.in_(wanted),
                    Attachment.user_id == owner_id,
                    Attachment.status == AttachmentStatus.READY,
                    or_(Attachment.expires_at.is_(None), Attachment.expires_at > datetime.now(UTC)),
                )
                .order_by(Attachment.id)
                .with_for_update()
                .execution_options(populate_existing=True)
            )
        )
        if len(rows) != len(wanted):
            raise ResourceNotFoundError("attachment")
        statement = insert(ConversationAttachmentUsage).values(
            [
                {
                    "attachment_id": row.id,
                    "conversation_id": target.id,
                    "conversation_revision": target.revision,
                }
                for row in rows
            ]
        )
        await self.db.execute(
            statement.on_conflict_do_update(
                constraint="uq_conversation_attachment_usage",
                set_={"conversation_revision": statement.excluded.conversation_revision},
            )
        )
        by_id = {row.id: row for row in rows}
        return [by_id[file_id] for file_id in dict.fromkeys(attachment_ids)]

    async def release_conversation_usages(self, target: ConversationRef) -> tuple[UUID, ...]:
        """Retire only uploads whose last accepted use this exact generation held.

        The lifecycle calls this BEFORE rotating/removing its source in the same
        transaction. The file row remains the durable cleanup intent: a crash or
        refused unlink must not lose the only copy of its immutable path.

        Args:
            target: Current generation being retired, after lifecycle admission.

        Returns:
            UUIDs newly changed to DELETING, excluding shared/generated/unknown files.

        Raises:
            ExecutionRevoked: The supplied source is no longer current.
        """
        await hold_conversation_source(self.db, target.owner_id, target)
        usage = ConversationAttachmentUsage
        ids = list(
            await self.db.scalars(
                select(Attachment.id)
                .join(usage, usage.attachment_id == Attachment.id)
                .where(
                    Attachment.user_id == target.owner_id,
                    usage.conversation_id == target.id,
                    usage.conversation_revision == target.revision,
                )
                .order_by(Attachment.id)
                .with_for_update(of=Attachment)
            )
        )
        if not ids:
            return ()
        await self.db.execute(
            delete(usage).where(
                usage.attachment_id.in_(ids),
                usage.conversation_id == target.id,
                usage.conversation_revision == target.revision,
            )
        )
        retired = await self.db.scalars(
            update(Attachment)
            .where(
                Attachment.id.in_(ids),
                Attachment.user_id == target.owner_id,
                Attachment.origin == AttachmentOrigin.UPLOAD.value,
                Attachment.status == AttachmentStatus.READY,
                ~exists().where(usage.attachment_id == Attachment.id),
            )
            .values(
                status=AttachmentStatus.DELETING,
                deletion_reason=DELETION_REASON_CONVERSATION_RESET,
            )
            .returning(Attachment.id)
        )
        return tuple(sorted(retired))
