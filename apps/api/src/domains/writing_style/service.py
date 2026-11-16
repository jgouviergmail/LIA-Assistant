"""The person's writing style, as the settings read and forget it (ADR-383).

Learning it is the person's own act, through the assists' door
(``tool_assists/style_learning``): this service only shows what was learned — in clear,
it is the person's own record — and forgets it at their word. A profile that can no
longer be read back (a rotated key) reads as nothing learned: the person learns it again.
"""

from __future__ import annotations

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
            The switch, how many sent e-mails a learning reads, and what was learned with
            when, if anything.

        Raises:
            BaseAPIException: The account does not exist.
        """
        stored = await self.repository.read(user_id)
        if stored is None:
            raise_user_not_found(user_id)
        assert stored is not None
        nothing = WritingStyleResponse(
            enabled=stored.enabled, mails_to_read=settings.writing_style_sent_mails
        )
        row = stored.row
        if row is None:
            return nothing
        profile: str | None = None
        if row.profile_encrypted is not None:
            try:
                profile = decrypt_data(row.profile_encrypted)
            except ValueError:
                logger.warning("writing_style_unreadable", user_id=str(user_id))
                return nothing
        return nothing.model_copy(
            update={"profile": profile, "mails_read": row.mails_read, "learned_at": row.built_at}
        )

    async def forget(self, user_id: UUID) -> bool:
        """Remove what was learned; nothing is learned again until the person asks.

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
