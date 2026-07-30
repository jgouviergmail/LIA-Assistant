"""Relation favorites repository — the CRM's only persisted state.

Add is an idempotent server-side UPSERT (starring twice refreshes the stored
spelling, never errors); remove reports whether a row actually existed so the
router can stay honest without a pre-SELECT.
"""

from uuid import UUID

from sqlalchemy import delete, select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from src.domains.relations.models import RelationFavorite


class RelationFavoriteRepository:
    """Data access for ``relation_favorites`` (one starred name per row)."""

    def __init__(self, db: AsyncSession) -> None:
        """Bind the repository to a request-scoped session.

        Args:
            db: Async session owned by the caller (router/service transaction).
        """
        self.db = db

    async def list_for_user(self, user_id: UUID) -> list[RelationFavorite]:
        """All favorites of one user, stable alphabetical order.

        Args:
            user_id: Owner of the stars.

        Returns:
            Favorites ordered by folded name key.
        """
        result = await self.db.execute(
            select(RelationFavorite)
            .where(RelationFavorite.user_id == user_id)
            .order_by(RelationFavorite.name_key)
        )
        return list(result.scalars().all())

    async def add(self, user_id: UUID, *, name_key: str, display_name: str) -> None:
        """Star a name — idempotent UPSERT refreshing the stored spelling.

        Args:
            user_id: Owner of the star.
            name_key: Folded identity key (``fold_name`` output).
            display_name: Spelling as the user starred it.
        """
        stmt = pg_insert(RelationFavorite).values(
            user_id=user_id, name_key=name_key, display_name=display_name
        )
        stmt = stmt.on_conflict_do_update(
            constraint="uq_relation_favorites_user_name",
            set_={"display_name": stmt.excluded.display_name},
        )
        await self.db.execute(stmt)
        await self.db.flush()

    async def remove(self, user_id: UUID, *, name_key: str) -> bool:
        """Unstar a name.

        Args:
            user_id: Owner of the star.
            name_key: Folded identity key.

        Returns:
            True when a row existed and was deleted.
        """
        result = await self.db.execute(
            delete(RelationFavorite).where(
                RelationFavorite.user_id == user_id,
                RelationFavorite.name_key == name_key,
            )
        )
        await self.db.flush()
        return bool(getattr(result, "rowcount", 0))
