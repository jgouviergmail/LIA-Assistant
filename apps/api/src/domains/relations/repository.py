"""Relations repositories — the CRM's only persisted state.

Two tables, both tiny: the stars a user set, and the merges they declared.

Favorites: add is an idempotent server-side UPSERT (starring twice refreshes
the stored spelling, never errors); remove reports whether a row actually
existed so the router can stay honest without a pre-SELECT.

Aliases: every write keeps the table FLAT — no alias ever points at another
alias — which is what lets every read resolve an identity in one lookup.
"""

from uuid import UUID

from sqlalchemy import delete, select, update
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from src.domains.relations.models import RelationAlias, RelationFavorite


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


class RelationAliasRepository:
    """Data access for ``relation_aliases`` (one merge per row).

    The table is kept FLAT — no ``alias_key`` is ever also a ``canonical_key``
    — which is what makes every read a single lookup, with no chain to walk.
    That invariant is held by TWO parties, and saying so matters because
    neither half is sufficient alone:

    - this repository compresses the paths that POINT AT the merged-away side
      (``merge`` repoints them in the same transaction);
    - the caller supplies a ``canonical_key`` it has already resolved through
      ``IdentityResolver``. Passing a key that is itself an alias would create
      the one chain nothing here can prevent.

    Two concurrent merges by the same user can still interleave into a chain
    (A→B committed while B→C was being computed). The effect is bounded and
    self-healing: a read resolves one hop, so the two identities show as two
    cards until the merge is redone — never a cycle, never a lost row. Serial
    use is the real-world case: the UI holds a single busy control.
    """

    def __init__(self, db: AsyncSession) -> None:
        """Bind the repository to a request-scoped session.

        Args:
            db: Async session owned by the caller (router/service transaction).
        """
        self.db = db

    async def list_for_user(self, user_id: UUID) -> list[RelationAlias]:
        """Every merge of one user, stable order.

        Args:
            user_id: Owner of the merges.

        Returns:
            Rows ordered by alias key.
        """
        result = await self.db.execute(
            select(RelationAlias)
            .where(RelationAlias.user_id == user_id)
            .order_by(RelationAlias.alias_key)
        )
        return list(result.scalars().all())

    async def merge(
        self, user_id: UUID, *, alias_key: str, canonical_key: str, alias_display_name: str
    ) -> None:
        """Record that ``alias_key`` is the same person as ``canonical_key``.

        Two writes, one transaction:

        1. every row already pointing at ``alias_key`` is repointed at
           ``canonical_key`` — this is the path compression that keeps the
           table flat when B (which already absorbed A) is merged into C;
        2. the merge itself, as an idempotent UPSERT: merging twice is a
           correction, not a second identity.

        Args:
            user_id: Owner of the merge.
            alias_key: Folded identity being merged AWAY.
            canonical_key: Folded identity it joins (already canonical).
            alias_display_name: Spelling of the merged-away side, so the undo
                can name what it is about to split back out.
        """
        await self.db.execute(
            update(RelationAlias)
            .where(
                RelationAlias.user_id == user_id,
                RelationAlias.canonical_key == alias_key,
            )
            .values(canonical_key=canonical_key)
        )
        stmt = pg_insert(RelationAlias).values(
            user_id=user_id,
            alias_key=alias_key,
            canonical_key=canonical_key,
            alias_display_name=alias_display_name,
        )
        stmt = stmt.on_conflict_do_update(
            constraint="uq_relation_aliases_user_alias",
            set_={
                "canonical_key": stmt.excluded.canonical_key,
                "alias_display_name": stmt.excluded.alias_display_name,
            },
        )
        await self.db.execute(stmt)
        await self.db.flush()

    async def split(self, user_id: UUID, *, alias_key: str) -> bool:
        """Undo one merge — the merged-away side becomes its own relationship.

        Nothing is rewritten in the sources, which always kept their own
        spellings, so the split half reappears exactly as it was.

        Args:
            user_id: Owner of the merge.
            alias_key: Folded identity to split back out.

        Returns:
            True when a merge existed and was undone.
        """
        result = await self.db.execute(
            delete(RelationAlias).where(
                RelationAlias.user_id == user_id,
                RelationAlias.alias_key == alias_key,
            )
        )
        await self.db.flush()
        return bool(getattr(result, "rowcount", 0))
