"""Ticket categories: the rules of an account's lanes (ADR-276).

A category is a name the OWNER of a board files tickets under; the board draws
one lane per name, and a ticket filed under nothing sits in the unfiled lane.

Three rules live here and nowhere else:

- **a name is an identity.** It is stored trimmed and single-spaced, and two
  names are the same category when ``fold_name`` says so (case, accents). The
  fold has one implementation (ADR-185); the stored ``name_key`` is its result
  and the unique constraint its backstop.
- **the category is the owner's** (owner arbitration, 2026-11-11). A ticket
  may only be filed under a category of ITS OWNER, by its owner. A peer who
  holds the ticket reads the lane; refiling it would be rewriting the owner's
  words about their own ticket, the same refusal as editing its title.
- **every write is serialised on the account** — the same fence a ticket
  creation takes. The cap, the uniqueness and the order are all read-then-
  write, and a deletion must not interleave with a ticket being filed under
  the category it removes.

Refusals are stable codes (:class:`WorkboardError`); a category the caller does
not own answers the neutral 404 an unknown one does.
"""

from __future__ import annotations

from collections.abc import Iterable
from uuid import UUID

import structlog
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.config import settings
from src.core.exceptions import raise_invalid_input, raise_not_found_or_unauthorized
from src.domains.peers.pair_fence import lock_peer_pair
from src.domains.shared.text_normalization import fold_name
from src.domains.users.models import User
from src.domains.workboard.board_queries import BoardFilters
from src.domains.workboard.category_repository import WorkboardCategoryRepository
from src.domains.workboard.constants import STATUS_ORDER, WorkboardError
from src.domains.workboard.models import WorkboardCategory, WorkboardTicket
from src.domains.workboard.repository import WorkboardRepository
from src.domains.workboard.schemas import (
    CategoryCreate,
    CategoryList,
    CategoryRow,
    CategoryUpdate,
    LaneRow,
)

logger = structlog.get_logger(__name__)


def _name_key(name: str) -> str:
    """The key a category's name is unique and looked up on.

    ONE spelling of it: the write that stores a name and the read that finds a
    category by its name fold through here, so a name the person says is found
    whatever its case, its accents or its spacing.

    Args:
        name: A name, as stored or as said.

    Returns:
        The folded key; empty for a blank name.
    """
    return fold_name(" ".join(name.split()))


def _clean_name(name: str) -> tuple[str, str]:
    """Validate a name against the published bound, and fold it.

    Args:
        name: What the caller sent.

    Returns:
        The name as stored — trimmed, runs of whitespace collapsed — and the
        key its uniqueness is held on.

    Raises:
        ValidationError: Blank, or longer than ``workboard_category_name_max_chars``.
    """
    cleaned = " ".join(name.split())
    key = _name_key(name)
    if not key:
        raise_invalid_input(WorkboardError.CATEGORY_NAME_REQUIRED.value)
    if len(cleaned) > settings.workboard_category_name_max_chars:
        raise_invalid_input(WorkboardError.CATEGORY_NAME_TOO_LONG.value)
    return cleaned, key


def _row(category: WorkboardCategory, ticket_count: int) -> CategoryRow:
    """One category as the API publishes it."""
    return CategoryRow(
        id=category.id,
        owner_user_id=category.owner_user_id,
        name=category.name,
        position=category.position,
        ticket_count=ticket_count,
    )


class WorkboardCategoryService:
    """Business rules of an account's ticket categories."""

    def __init__(self, db: AsyncSession) -> None:
        self.db = db
        self.repo = WorkboardCategoryRepository(db)

    # ------------------------------------------------------------------ reads

    async def listing(self, actor: User) -> CategoryList:
        """Every category on the reader's board, with the caps of this instance.

        Args:
            actor: The reader.

        Returns:
            Their own categories first, then those of the tickets they hold for
            somebody else, each with its exact ticket count.
        """
        visible = await self.repo.list_visible(actor.id)
        counts = await self.repo.ticket_counts(actor.id) if visible else {}
        return CategoryList(
            categories=[_row(category, counts.get(category.id, 0)) for category in visible],
            max_categories=settings.workboard_max_categories_per_user,
            name_max_chars=settings.workboard_category_name_max_chars,
        )

    async def lanes(self, actor: User, filters: BoardFilters) -> list[LaneRow]:
        """The board's lanes, with one exact count per lane and per column.

        Empty for a reader with no category in sight, and then no aggregate is
        run at all: the board draws what it drew before categories existed.

        Args:
            actor: The reader.
            filters: The SAME filters the page is read with.

        Returns:
            The unfiled lane first, then the reader's own categories in their
            order, then the others'.
        """
        visible = await self.repo.list_visible(actor.id)
        if not visible:
            return []
        counts = await self.repo.lane_counts(
            WorkboardRepository(self.db).filtered_stmt(actor.id, filters)
        )

        def lane(category: WorkboardCategory | None) -> LaneRow:
            key = None if category is None else category.id
            return LaneRow(
                category_id=key,
                name=None if category is None else category.name,
                owner_user_id=None if category is None else category.owner_user_id,
                counts_by_status={status: counts.get((key, status), 0) for status in STATUS_ORDER},
            )

        return [lane(None), *(lane(category) for category in visible)]

    # ----------------------------------------------------------------- writes

    async def _owned_for_write(self, actor: User) -> list[WorkboardCategory]:
        """Take the account fence, then read the account's categories.

        The fence FIRST: every rule below reads this list and writes from it.

        Args:
            actor: The caller.

        Returns:
            Their own categories, in order.
        """
        # One account on both sides: the fence a ticket creation takes for an
        # unassigned ticket, so filing a ticket and removing its lane queue up.
        await lock_peer_pair(self.db, actor.id, actor.id)
        return await self.repo.list_owned(actor.id)

    @staticmethod
    def _find(owned: list[WorkboardCategory], category_id: UUID) -> WorkboardCategory:
        """One of the caller's own categories, or the neutral 404.

        Args:
            owned: The caller's categories.
            category_id: The one asked for.

        Returns:
            The row.

        Raises:
            ResourceNotFoundError: Unknown, or somebody else's — the same answer.
        """
        for category in owned:
            if category.id == category_id:
                return category
        raise_not_found_or_unauthorized("category", category_id)

    async def create(self, actor: User, data: CategoryCreate) -> CategoryRow:
        """Add a category to the caller's board.

        Args:
            actor: The owner-to-be.
            data: The request.

        Returns:
            The created category, flushed — the caller owns the commit.

        Raises:
            ValidationError: A name rule, a name already taken, or the cap.
        """
        owned = await self._owned_for_write(actor)
        name, key = _clean_name(data.name)
        if any(category.name_key == key for category in owned):
            raise_invalid_input(WorkboardError.CATEGORY_NAME_TAKEN.value)
        if len(owned) >= settings.workboard_max_categories_per_user:
            raise_invalid_input(WorkboardError.TOO_MANY_CATEGORIES.value)
        position = len(owned) if data.position is None else min(data.position, len(owned))
        category = await self.repo.create(
            {"owner_user_id": actor.id, "name": name, "name_key": key, "position": position}
        )
        if position < len(owned):
            ordered = [existing.id for existing in owned]
            ordered.insert(position, category.id)
            await self.repo.renumber(actor.id, ordered)
        logger.info(
            "workboard_category_created", category_id=str(category.id), owner_id=str(actor.id)
        )
        return _row(category, 0)

    async def update(self, actor: User, category_id: UUID, data: CategoryUpdate) -> CategoryRow:
        """Rename a category, move it among the caller's own, or both.

        Args:
            actor: The caller.
            category_id: The category.
            data: What to change.

        Returns:
            The updated category, not yet committed.

        Raises:
            ValidationError: A name rule, or a name already taken.
            ResourceNotFoundError: Unknown or not theirs.
        """
        owned = await self._owned_for_write(actor)
        category = self._find(owned, category_id)
        if data.name is not None:
            name, key = _clean_name(data.name)
            if any(other.name_key == key and other.id != category.id for other in owned):
                raise_invalid_input(WorkboardError.CATEGORY_NAME_TAKEN.value)
            category.name, category.name_key = name, key
        if data.position is not None:
            ordered = [other.id for other in owned if other.id != category.id]
            ordered.insert(min(data.position, len(ordered)), category.id)
            await self.repo.renumber(actor.id, ordered)
            category.position = ordered.index(category.id)
        await self.db.flush()
        return _row(category, await self.repo.count_tickets(category.id))

    async def delete(self, actor: User, category_id: UUID) -> int:
        """Remove a category; its tickets go back to the unfiled lane.

        No ticket is deleted: the foreign key sets ``category_id`` to NULL on
        every ticket filed under it, whoever holds them.

        Args:
            actor: The caller.
            category_id: The category.

        Returns:
            How many tickets it released, counted before the removal.

        Raises:
            ResourceNotFoundError: Unknown or not theirs.
        """
        owned = await self._owned_for_write(actor)
        category = self._find(owned, category_id)
        released = await self.repo.count_tickets(category.id)
        await self.db.delete(category)
        await self.db.flush()
        await self.repo.renumber(actor.id, [other.id for other in owned if other.id != category.id])
        logger.info(
            "workboard_category_deleted",
            category_id=str(category_id),
            owner_id=str(actor.id),
            released_tickets=released,
        )
        return released

    # ------------------------------------------------------- filing a ticket

    async def _require_owned(self, owner_id: UUID, category_id: UUID) -> UUID:
        """The category's id, once it is known to be this owner's own.

        Args:
            owner_id: Whose it must be.
            category_id: The category named.

        Returns:
            The id.

        Raises:
            ValidationError: Unknown, or somebody else's.
        """
        category = await self.repo.get_owned(category_id, owner_id)
        if category is None:
            raise_invalid_input(WorkboardError.CATEGORY_UNKNOWN.value)
        return category.id

    async def creation_category(
        self, owner_id: UUID, category_id: UUID | None, parent: WorkboardTicket | None
    ) -> UUID | None:
        """The category a new ticket is born in.

        A category named explicitly must be the owner's. With none named, a
        step is born in its parent's lane: a step landing in the unfiled lane,
        away from the ticket it is a step of, would undo the reading the lanes
        exist to give. The rule is idempotent on purpose — the assistant's
        confirmation replays it on an already-normalised request.

        Args:
            owner_id: The owner-to-be.
            category_id: The category the request named, or None.
            parent: The parent ticket, when the new one is a step.

        Returns:
            The category to store, or None.

        Raises:
            ValidationError: A category that is not the owner's.
        """
        if category_id is not None:
            return await self._require_owned(owner_id, category_id)
        return None if parent is None else parent.category_id

    async def own_named(self, owner_id: UUID, name: str) -> UUID:
        """The account's own category of that name — what a ticket is FILED under.

        Read among the actor's OWN categories and nowhere else: a name of
        somebody else's is simply not found, so no refusal ever says whether
        another account has a category called that.

        Args:
            owner_id: Whose categories.
            name: The name as the person says it; case and accents are folded.

        Returns:
            The category's id.

        Raises:
            ValidationError: ``workboard_category_unknown``.
        """
        key = _name_key(name)
        for category in await self.repo.list_owned(owner_id):
            if category.name_key == key:
                return category.id
        raise_invalid_input(WorkboardError.CATEGORY_UNKNOWN.value)

    async def visible_named(self, user_id: UUID, name: str) -> tuple[UUID, ...]:
        """Every lane of that name on the reader's board — what a board is NARROWED to.

        Theirs and those of the tickets they hold: two people may both have a
        « Home », and the reader who asks for it asked for both.

        Args:
            user_id: The reader.
            name: The name as the person says it; case and accents are folded.

        Returns:
            At least one category id.

        Raises:
            ValidationError: ``workboard_category_unknown`` — « no ticket in
                Garden » and « no category Garden » are not the same answer,
                and an empty page would say the first.
        """
        key = _name_key(name)
        found = tuple(
            category.id
            for category in await self.repo.list_visible(user_id)
            if category.name_key == key
        )
        if not found:
            raise_invalid_input(WorkboardError.CATEGORY_UNKNOWN.value)
        return found

    async def names_for(self, user_id: UUID, tickets: Iterable[WorkboardTicket]) -> dict[UUID, str]:
        """Name the categories some tickets are filed under.

        What every surface OFF the board shows beside a ticket: on the board
        a card sits in its lane, elsewhere the lane is a badge. One question
        for the whole page, and none when nothing on it is filed.

        Args:
            user_id: The reader — a name is read only from their own board.
            tickets: The page.

        Returns:
            Name by category id; a category that is gone is simply absent.
        """
        wanted = {ticket.category_id for ticket in tickets if ticket.category_id is not None}
        return await self.repo.names(user_id, wanted) if wanted else {}

    async def file(
        self, ticket: WorkboardTicket, actor_id: UUID, category_id: UUID | None, *, clear: bool
    ) -> None:
        """File a ticket under a category, or take it out — the owner only.

        Nothing asked changes nothing, and reads nothing.

        Args:
            ticket: The row being edited.
            actor_id: The caller.
            category_id: The category to file under, or None.
            clear: Whether to take the ticket out of its category.

        Raises:
            ValidationError: A holder refiling the owner's ticket, or a
                category that is not the owner's.
        """
        if category_id is None and not clear:
            return
        if ticket.owner_user_id != actor_id:
            raise_invalid_input(WorkboardError.PEER_CANNOT_EDIT_FIELD.value)
        ticket.category_id = (
            None
            if clear or category_id is None
            else await self._require_owned(actor_id, category_id)
        )


__all__ = ["WorkboardCategoryService"]
