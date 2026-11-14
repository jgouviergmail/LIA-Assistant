"""
Attachment repository for database operations.

Extends BaseRepository with attachment-specific queries:
- Batch fetch with ownership check
- Ready file and gallery projections

Durable retirement and disk claims live in AttachmentFileRepository.

Phase: evolution F4 — File Attachments & Vision Analysis
Created: 2026-03-09
"""

import uuid
from datetime import UTC, datetime
from typing import TYPE_CHECKING

import structlog
from sqlalchemy import func, or_, select
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

        Only returns the owner's ready files before their deadline, or explicitly
        kept files with no deadline. Used by ChatRequest to validate attachment_ids.

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
            or_(Attachment.expires_at.is_(None), Attachment.expires_at > datetime.now(UTC)),
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

    async def kept_totals(self) -> tuple[int, int]:
        """How many files people kept, and the bytes they hold (instance-wide).

        Returns:
            ``(files, bytes)``.
        """
        row = (
            await self.db.execute(
                select(
                    func.count(Attachment.id), func.coalesce(func.sum(Attachment.file_size), 0)
                ).where(
                    Attachment.expires_at.is_(None), Attachment.status == AttachmentStatus.READY
                )
            )
        ).one()
        return int(row[0] or 0), int(row[1] or 0)

    async def newest_by_filename(
        self, user_id: uuid.UUID, filename: str, now: datetime
    ) -> Attachment | None:
        """The file an account's name designates, among those that can still be read.

        Args:
            user_id: Whose files.
            filename: The exact name, as the attachment hint and the gallery show it.
            now: Past its deadline a file is about to go, and is not offered.

        Returns:
            The newest such file, or None.
        """
        stmt = (
            select(Attachment)
            .where(
                Attachment.user_id == user_id,
                Attachment.original_filename == filename,
                Attachment.status == AttachmentStatus.READY,
                or_(Attachment.expires_at.is_(None), Attachment.expires_at > now),
            )
            .order_by(Attachment.created_at.desc(), Attachment.id.desc())
            .limit(1)
        )
        return (await self.db.execute(stmt)).scalar_one_or_none()

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
