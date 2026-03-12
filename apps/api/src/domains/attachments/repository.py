"""
Attachment repository for database operations.

Extends BaseRepository with attachment-specific queries:
- Batch fetch with ownership check
- Expired attachments query for cleanup
- Bulk delete for user (conversation reset)

Phase: evolution F4 — File Attachments & Vision Analysis
Created: 2026-03-09
"""

import uuid
from datetime import datetime

import structlog
from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.repository import BaseRepository
from src.domains.attachments.models import Attachment, AttachmentStatus

logger = structlog.get_logger(__name__)


class AttachmentRepository(BaseRepository[Attachment]):
    """Repository for Attachment model with domain-specific queries."""

    def __init__(self, db: AsyncSession) -> None:
        super().__init__(db, Attachment)

    async def get_batch_for_user(
        self,
        ids: list[uuid.UUID],
        user_id: uuid.UUID,
    ) -> list[Attachment]:
        """
        Fetch multiple attachments by IDs with ownership verification.

        Only returns attachments that belong to the specified user and have
        status 'ready'. Used by ChatRequest to validate attachment_ids.

        Args:
            ids: List of attachment UUIDs to fetch.
            user_id: Owner user UUID (ownership check).

        Returns:
            List of matching Attachment instances (may be shorter than ids
            if some are missing, expired, or belong to another user).
        """
        if not ids:
            return []

        stmt = select(Attachment).where(
            Attachment.id.in_(ids),
            Attachment.user_id == user_id,
            Attachment.status == AttachmentStatus.READY,
        )
        result = await self.db.execute(stmt)
        attachments = list(result.scalars().all())

        logger.debug(
            "attachments_batch_fetched",
            requested=len(ids),
            found=len(attachments),
            user_id=str(user_id),
        )

        return attachments

    async def get_expired(self, now: datetime) -> list[Attachment]:
        """
        Fetch all attachments past their expiration time.

        Used by the cleanup scheduler to find orphan or expired files.

        Args:
            now: Current UTC datetime.

        Returns:
            List of expired Attachment instances.
        """
        stmt = select(Attachment).where(
            Attachment.expires_at <= now,
            Attachment.status != AttachmentStatus.EXPIRED,
        )
        result = await self.db.execute(stmt)
        return list(result.scalars().all())

    async def delete_for_user(self, user_id: uuid.UUID) -> int:
        """
        Delete all attachments for a user (conversation reset).

        Caller must fetch file paths beforehand via get_file_paths_for_user()
        for disk cleanup.

        Args:
            user_id: User UUID.

        Returns:
            Number of deleted records.
        """
        stmt = delete(Attachment).where(Attachment.user_id == user_id)
        result = await self.db.execute(stmt)
        count: int = result.rowcount  # type: ignore[attr-defined]

        logger.info(
            "attachments_deleted_for_user",
            user_id=str(user_id),
            count=count,
        )

        return count

    async def get_file_paths_for_user(self, user_id: uuid.UUID) -> list[str]:
        """
        Get all file paths for a user (for disk cleanup before DB delete).

        Args:
            user_id: User UUID.

        Returns:
            List of relative file paths.
        """
        stmt = select(Attachment.file_path).where(Attachment.user_id == user_id)
        result = await self.db.execute(stmt)
        return list(result.scalars().all())
