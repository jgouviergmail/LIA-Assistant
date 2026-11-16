"""Reads and writes of the writing-style profile (ADR-383).

One row per account. A profile is kept only while the person's switch is ON at the
moment of writing, and only in place of the record the person asked to replace: a
learning started before they switched it off, or before they forgot what was learned,
writes nothing — in the same statement, with no window between a check and the write.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from uuid import UUID, uuid4

from sqlalchemy import DateTime, Integer, Text, delete, exists, literal, select, update
from sqlalchemy.dialects.postgresql import UUID as PG_UUID
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.repository import BaseRepository
from src.domains.users.models import User
from src.domains.writing_style.models import WritingStyle


@dataclass(frozen=True, slots=True)
class StoredStyle:
    """The account's switch and its profile row, read together.

    Attributes:
        enabled: The person's switch (``users.writing_style_enabled``).
        row: The profile row, or None when nothing was ever learned.
    """

    enabled: bool
    row: WritingStyle | None


class WritingStyleRepository(BaseRepository[WritingStyle]):
    """The writing-style profiles, one per account."""

    def __init__(self, db: AsyncSession) -> None:
        """Bind the repository to a session.

        Args:
            db: The session the reads and writes run on.
        """
        super().__init__(db, WritingStyle)

    async def read(self, user_id: UUID) -> StoredStyle | None:
        """The account's switch and its profile row, in one statement.

        Args:
            user_id: The account.

        Returns:
            Both, or None when the account does not exist.
        """
        result = await self.db.execute(
            select(User.writing_style_enabled, WritingStyle)
            .outerjoin(WritingStyle, WritingStyle.user_id == User.id)
            .where(User.id == user_id)
        )
        found = result.one_or_none()
        if found is None:
            return None
        return StoredStyle(enabled=bool(found[0]), row=found[1])

    async def save(
        self,
        user_id: UUID,
        *,
        profile_encrypted: str | None,
        mails_read: int,
        built_at: datetime,
        replaces: datetime | None,
    ) -> bool:
        """Keep the profile just learned in place of the record the person asked on.

        Both conditions sit in the write itself: the switch is ON, and the record the
        learning replaces still stands — ``replaces`` names it, None when nothing was
        learned. A record forgotten or learned again meanwhile is the person's later
        act: it stands, and nothing is written (amendment 2026-11-16).

        Args:
            user_id: The account.
            profile_encrypted: The encrypted profile, or None when nothing was learned.
            mails_read: How many sent e-mails it was learned from.
            built_at: When it was learned (aware).
            replaces: When the record it replaces was learned (aware), or None when the
                person asked with nothing learned.

        Returns:
            Whether it was kept (False: the switch was off, or the record had changed).
        """
        now = datetime.now(UTC)
        switched_on = exists().where(User.id == user_id, User.writing_style_enabled.is_(True))
        if replaces is not None:
            replaced = await self.db.execute(
                update(WritingStyle)
                .where(
                    WritingStyle.user_id == user_id,
                    WritingStyle.built_at == replaces,
                    switched_on,
                )
                .values(
                    profile_encrypted=profile_encrypted,
                    mails_read=mails_read,
                    built_at=built_at,
                    updated_at=now,
                )
            )
            return bool(getattr(replaced, "rowcount", 0))
        source = select(
            literal(uuid4(), PG_UUID(as_uuid=True)),
            literal(user_id, PG_UUID(as_uuid=True)),
            literal(profile_encrypted, Text()),
            literal(mails_read, Integer()),
            literal(built_at, DateTime(timezone=True)),
            literal(now, DateTime(timezone=True)),
            literal(now, DateTime(timezone=True)),
        ).where(switched_on)
        statement = pg_insert(WritingStyle).from_select(
            [
                WritingStyle.id,
                WritingStyle.user_id,
                WritingStyle.profile_encrypted,
                WritingStyle.mails_read,
                WritingStyle.built_at,
                WritingStyle.created_at,
                WritingStyle.updated_at,
            ],
            source,
        )
        # Asked with nothing learned: a record standing now was written since — kept.
        inserted = await self.db.execute(
            statement.on_conflict_do_nothing(index_elements=[WritingStyle.user_id])
        )
        return bool(getattr(inserted, "rowcount", 0))

    async def forget(self, user_id: UUID, *, learned_at: datetime | None = None) -> bool:
        """Remove what was learned about how the account writes.

        Args:
            user_id: The account.
            learned_at: When given, remove that very record only — the one a card showed —
                in the same statement: a record learned since is another one, kept.

        Returns:
            Whether there was a profile to remove (the one named, when named).
        """
        statement = delete(WritingStyle).where(WritingStyle.user_id == user_id)
        if learned_at is not None:
            statement = statement.where(WritingStyle.built_at == learned_at)
        result = await self.db.execute(statement)
        return bool(getattr(result, "rowcount", 0))


__all__ = ["StoredStyle", "WritingStyleRepository"]
