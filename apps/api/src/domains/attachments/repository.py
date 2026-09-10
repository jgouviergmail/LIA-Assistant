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
from collections.abc import Collection
from datetime import datetime
from typing import TYPE_CHECKING

import structlog
from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.repository import BaseRepository
from src.domains.attachments.models import Attachment, AttachmentStatus

if TYPE_CHECKING:
    from src.domains.attachments.gallery_queries import GalleryFilters

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

    async def delete_for_user(
        self, user_id: uuid.UUID, *, origins: Collection[str] | None = None
    ) -> int:
        """
        Delete a user's attachments, optionally narrowed to some origins.

        Caller must fetch file paths beforehand via get_file_paths_for_user()
        for disk cleanup — with the SAME narrowing, or the disk loses files the
        database keeps.

        Args:
            user_id: User UUID.
            origins: Producers to remove; None removes everything (account
                deletion). A conversation reset passes ``{upload}`` alone: a
                file LIA produced survives the conversation it was produced in
                (ADR-279, owner arbitration 2026-09-10).

        Returns:
            Number of deleted records.
        """
        stmt = delete(Attachment).where(Attachment.user_id == user_id)
        if origins is not None:
            stmt = stmt.where(Attachment.origin.in_(list(origins)))
        result = await self.db.execute(stmt)
        count: int = result.rowcount  # type: ignore[attr-defined]

        logger.info(
            "attachments_deleted_for_user",
            user_id=str(user_id),
            count=count,
            origins=sorted(origins) if origins is not None else None,
        )

        return count

    async def get_file_paths_for_user(
        self, user_id: uuid.UUID, *, origins: Collection[str] | None = None
    ) -> list[str]:
        """
        Get file paths for a user (for disk cleanup before DB delete).

        Args:
            user_id: User UUID.
            origins: Same narrowing as :meth:`delete_for_user` — the two must
                agree or the disk loses files the database keeps.

        Returns:
            List of relative file paths.
        """
        stmt = select(Attachment.file_path).where(Attachment.user_id == user_id)
        if origins is not None:
            stmt = stmt.where(Attachment.origin.in_(list(origins)))
        result = await self.db.execute(stmt)
        return list(result.scalars().all())

    async def list_generated(
        self, user_id: uuid.UUID, filters: GalleryFilters
    ) -> tuple[list[Attachment], int, int]:
        """One page of a gallery, its EXACT total and the bytes behind it.

        The rows and the count come from the SAME filtered statement
        (`gallery_queries`, ADR-185): built apart, the total eventually
        describes a different set from the rows.

        Args:
            user_id: Whose gallery.
            filters: What it is narrowed to.

        Returns:
            ``(rows, total, total_bytes)`` — the two figures over the whole
            filtered set, never over the page.
        """
        from sqlalchemy import func

        from src.domains.attachments.gallery_queries import build_gallery_statement

        rows = list((await self.db.execute(build_gallery_statement(user_id, filters))).scalars())
        count_statement = build_gallery_statement(user_id, filters, count=True)
        total = int((await self.db.execute(count_statement)).scalar() or 0)
        # The same WHERE, summed rather than counted: a gallery states how much
        # space it holds, and a sum over the page would under-report it.
        bytes_statement = count_statement.with_only_columns(
            func.coalesce(func.sum(Attachment.file_size), 0)
        )
        total_bytes = int((await self.db.execute(bytes_statement)).scalar() or 0)
        return rows, total, total_bytes

    async def get_owned_batch(self, ids: list[uuid.UUID], user_id: uuid.UUID) -> list[Attachment]:
        """The rows of ``ids`` this user owns, whatever their status.

        Unlike :meth:`get_batch_for_user`, no status filter: a person deletes a
        file of theirs even once it is marked expired.

        Args:
            ids: Candidate ids.
            user_id: Owner.

        Returns:
            The owned rows; a missing or foreign id is simply absent.
        """
        from sqlalchemy import select as _select

        if not ids:
            return []
        statement = _select(Attachment).where(Attachment.id.in_(ids), Attachment.user_id == user_id)
        return list((await self.db.execute(statement)).scalars())
