"""The person's writing style, as the settings read and forget it (ADR-383).

Learning it is the writers' door (``agents/emails/writing_style``): this service only
shows what was learned — in clear, it is the person's own record — and forgets it at
their word. A profile that can no longer be read back (a rotated key) reads as nothing
learned: the next e-mail LIA writes learns it again.
"""

from __future__ import annotations

from datetime import timedelta
from uuid import UUID

import structlog
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.config import settings
from src.core.exceptions import raise_user_not_found
from src.core.security.utils import decrypt_data
from src.domains.writing_style.repository import WritingStyleRepository
from src.domains.writing_style.schemas import WritingStyleResponse

logger = structlog.get_logger(__name__)


class WritingStyleService:
    """Read and forget what LIA learned of how an account writes."""

    def __init__(self, db: AsyncSession) -> None:
        """Bind the service to a session.

        Args:
            db: The request's session.
        """
        self.db = db
        self.repository = WritingStyleRepository(db)

    async def read(self, user_id: UUID) -> WritingStyleResponse:
        """What the settings show.

        Args:
            user_id: The account.

        Returns:
            The switch, and what was learned with when, if anything.

        Raises:
            BaseAPIException: The account does not exist.
        """
        stored = await self.repository.read(user_id)
        if stored is None:
            raise_user_not_found(user_id)
        assert stored is not None
        row = stored.row
        if row is None:
            return WritingStyleResponse(enabled=stored.enabled)
        profile: str | None = None
        if row.profile_encrypted is not None:
            try:
                profile = decrypt_data(row.profile_encrypted)
            except ValueError:
                logger.warning("writing_style_unreadable", user_id=str(user_id))
                return WritingStyleResponse(enabled=stored.enabled)
        return WritingStyleResponse(
            enabled=stored.enabled,
            profile=profile,
            mails_read=row.mails_read,
            learned_at=row.built_at,
            renews_at=row.built_at + timedelta(days=settings.writing_style_max_age_days),
        )

    async def forget(self, user_id: UUID) -> bool:
        """Remove what was learned; with the switch on, the next e-mail learns it again.

        Args:
            user_id: The account.

        Returns:
            Whether there was something to forget.
        """
        removed = await self.repository.forget(user_id)
        await self.db.commit()
        logger.info("writing_style_forgotten", user_id=str(user_id), removed=removed)
        return removed


__all__ = ["WritingStyleService"]
