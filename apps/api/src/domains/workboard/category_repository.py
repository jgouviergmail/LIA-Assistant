"""Reads and writes of ticket categories — the lanes of a board (ADR-276).

Kept beside the ticket repository rather than inside it: that file is at its
size cap, and the cut is not arbitrary — everything here answers « which lanes,
in which order, holding how many », and nothing here knows a run, a claim or a
comment.

Two properties every statement below keeps:

- **a lane's count is an aggregate over the page's OWN filter** (ADR-185). The
  counts statement is derived from the filtered statement the page itself uses
  (``WorkboardRepository.filtered_stmt``), never rebuilt: two spellings of the
  filter would let a lane's header disagree with the cards under it;
- **whose categories a reader sees has one spelling** (:meth:`visible_stmt`):
  their own, plus the categories of the tickets they hold for somebody else —
  never the rest of that person's vocabulary.
"""

from __future__ import annotations

from collections.abc import Collection
from uuid import UUID

from sqlalchemy import ColumnElement, Select, case, func, or_, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.repository import BaseRepository
from src.domains.workboard.board_queries import visible_predicate
from src.domains.workboard.models import WorkboardCategory, WorkboardTicket

#: A lane's key in the counts: the category, or None for the unfiled lane.
LaneKey = tuple[UUID | None, str]


class WorkboardCategoryRepository(BaseRepository[WorkboardCategory]):
    """Reads and writes of the categories tickets are filed under."""

    def __init__(self, db: AsyncSession) -> None:
        super().__init__(db, WorkboardCategory)

    # ------------------------------------------------------------- statements

    @staticmethod
    def on_board_of(user_id: UUID) -> ColumnElement[bool]:
        """Whether a category is on this reader's board — the ONE spelling.

        Their own, plus the category of any ticket they hold for somebody
        else: that one lane, and nothing else of its owner's vocabulary.

        Args:
            user_id: The reader.

        Returns:
            The predicate over ``workboard_categories``.
        """
        held = select(WorkboardTicket.category_id).where(
            WorkboardTicket.assignee_user_id == user_id,
            WorkboardTicket.category_id.is_not(None),
        )
        return or_(WorkboardCategory.owner_user_id == user_id, WorkboardCategory.id.in_(held))

    def visible_stmt(self, user_id: UUID) -> Select[tuple[WorkboardCategory]]:
        """Every category on this reader's board, their own first.

        A ticket somebody else owns is filed under ITS OWNER's category, so a
        reader who holds such a ticket sees that one category — the lane the
        ticket sits in — and nothing else of its owner's.

        The order is total: the reader's own before anybody else's, then one
        owner at a time, each in its own order, and the primary key last.

        Args:
            user_id: The reader.

        Returns:
            The ordered statement.
        """
        return (
            select(WorkboardCategory)
            .where(self.on_board_of(user_id))
            .order_by(
                (WorkboardCategory.owner_user_id != user_id).asc(),
                WorkboardCategory.owner_user_id.asc(),
                WorkboardCategory.position.asc(),
                WorkboardCategory.id.asc(),
            )
        )

    def names_stmt(self, user_id: UUID, category_ids: Collection[UUID]) -> Select[tuple[UUID, str]]:
        """The names of some categories, among those on this reader's board.

        A name is its owner's text: an id from anywhere else answers nothing,
        whoever asks — the visibility is read here, never trusted from the
        caller's list.

        Args:
            user_id: The reader.
            category_ids: The categories to name.

        Returns:
            Id and name, unordered.
        """
        return select(WorkboardCategory.id, WorkboardCategory.name).where(
            self.on_board_of(user_id), WorkboardCategory.id.in_(category_ids)
        )

    def lane_counts_stmt(
        self, filtered: Select[tuple[WorkboardTicket]]
    ) -> Select[tuple[UUID | None, str, int]]:
        """One exact count per lane and per column, over the page's own filter.

        Args:
            filtered: The statement the page itself is read from.

        Returns:
            The grouped aggregate, unordered.
        """
        return (
            filtered.order_by(None)
            .with_only_columns(WorkboardTicket.category_id, WorkboardTicket.status, func.count())
            .group_by(WorkboardTicket.category_id, WorkboardTicket.status)
        )

    # ------------------------------------------------------------------ reads

    async def list_owned(self, owner_id: UUID) -> list[WorkboardCategory]:
        """The account's own categories, in its order.

        Args:
            owner_id: Whose categories.

        Returns:
            Every one of them — the cap bounds the list.
        """
        stmt = (
            select(WorkboardCategory)
            .where(WorkboardCategory.owner_user_id == owner_id)
            .order_by(WorkboardCategory.position.asc(), WorkboardCategory.id.asc())
        )
        return list((await self.db.execute(stmt)).scalars().all())

    async def list_visible(self, user_id: UUID) -> list[WorkboardCategory]:
        """Every category on this reader's board (see :meth:`visible_stmt`).

        Args:
            user_id: The reader.

        Returns:
            Their own first, then the others'.
        """
        return list((await self.db.execute(self.visible_stmt(user_id))).scalars().all())

    async def names(self, user_id: UUID, category_ids: Collection[UUID]) -> dict[UUID, str]:
        """Name some categories of this reader's board (see :meth:`names_stmt`).

        Args:
            user_id: The reader.
            category_ids: The categories to name.

        Returns:
            One entry per category found; one that is gone is simply absent.
        """
        rows = (await self.db.execute(self.names_stmt(user_id, category_ids))).all()
        return {row.id: row.name for row in rows}

    async def get_owned(self, category_id: UUID, owner_id: UUID) -> WorkboardCategory | None:
        """The category, if it is this account's own.

        Args:
            category_id: The category.
            owner_id: Whose it must be.

        Returns:
            The row, or None — unknown and somebody else's answer alike.
        """
        stmt = select(WorkboardCategory).where(
            WorkboardCategory.id == category_id, WorkboardCategory.owner_user_id == owner_id
        )
        return (await self.db.execute(stmt)).scalar_one_or_none()

    async def count_tickets(self, category_id: UUID) -> int:
        """How many tickets are filed under a category, whoever holds them.

        Args:
            category_id: The category.

        Returns:
            The exact count — what a deletion would send back to the unfiled lane.
        """
        stmt = (
            select(func.count())
            .select_from(WorkboardTicket)
            .where(WorkboardTicket.category_id == category_id)
        )
        return int((await self.db.execute(stmt)).scalar() or 0)

    async def ticket_counts(self, user_id: UUID) -> dict[UUID, int]:
        """Exact number of tickets per category, over this reader's whole board.

        Args:
            user_id: The reader.

        Returns:
            One entry per category holding at least one visible ticket.
        """
        stmt = (
            select(WorkboardTicket.category_id, func.count())
            .where(visible_predicate(user_id), WorkboardTicket.category_id.is_not(None))
            .group_by(WorkboardTicket.category_id)
        )
        return {
            category_id: int(count) for category_id, count in (await self.db.execute(stmt)).all()
        }

    async def lane_counts(self, filtered: Select[tuple[WorkboardTicket]]) -> dict[LaneKey, int]:
        """Exact count per (lane, column) over the page's own filter.

        Args:
            filtered: The statement the page itself is read from.

        Returns:
            One entry per non-empty cell; the caller zero-fills the rest.
        """
        rows = (await self.db.execute(self.lane_counts_stmt(filtered))).all()
        return {(category_id, str(status)): int(count) for category_id, status, count in rows}

    # ----------------------------------------------------------------- writes

    async def renumber(self, owner_id: UUID, ordered_ids: list[UUID]) -> None:
        """Write the order of an account's categories in ONE statement.

        Dense from 0, like a column's cards: a row-by-row update would be N
        round trips and a window in which two lanes share a position.

        The rows already loaded in the session are deliberately NOT
        synchronised: synchronising a ``CASE`` falls back to expiring the
        attribute, and an expired attribute read after the fact is a lazy load
        an async session refuses. The caller sets the one position it returns.

        Args:
            owner_id: Whose categories.
            ordered_ids: Every one of them, in the new order.
        """
        if not ordered_ids:
            return
        mapping = {category_id: index for index, category_id in enumerate(ordered_ids)}
        await self.db.execute(
            update(WorkboardCategory)
            .where(
                WorkboardCategory.owner_user_id == owner_id,
                WorkboardCategory.id.in_(ordered_ids),
            )
            .values(
                position=case(mapping, value=WorkboardCategory.id, else_=WorkboardCategory.position)
            )
            .execution_options(synchronize_session=False)
        )


__all__ = ["LaneKey", "WorkboardCategoryRepository"]
