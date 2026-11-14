"""Ticket categories: the account's own lanes, and how a ticket is filed (ADR-276).

A category is a NAME the owner of a board files tickets under, and the board
draws one lane per name. Three rules are pinned here, each of them a way the
feature would otherwise lie:

- **a name is an identity**: two spellings of one name (case, accents, runs of
  spaces) are the same category, decided by ``fold_name`` and nothing else;
- **the category is the OWNER's**: a peer who merely holds a ticket reads its
  lane and cannot move the ticket out of it;
- **a lane's count is an aggregate over the page's own filter** (ADR-185), so
  the header of a lane can never disagree with the cards under it.
"""

from __future__ import annotations

import uuid
from collections.abc import Iterator
from dataclasses import dataclass
from unittest.mock import AsyncMock, patch

import pytest

from src.core.config import settings
from src.core.exceptions import BaseAPIException, ResourceNotFoundError
from src.domains.shared.text_normalization import fold_name
from src.domains.users.models import User
from src.domains.workboard.board_queries import BoardFilters
from src.domains.workboard.category_service import WorkboardCategoryService
from src.domains.workboard.constants import STATUS_ORDER, WorkboardError
from src.domains.workboard.models import WorkboardCategory, WorkboardTicket
from src.domains.workboard.schemas import CategoryCreate, CategoryUpdate

pytestmark = pytest.mark.unit

OWNER = uuid.uuid4()
PEER = uuid.uuid4()


def _user(user_id: uuid.UUID) -> User:
    return User(id=user_id, email=f"unit-{user_id}@example.test", is_active=True)


def _category(
    name: str = "Home", *, owner: uuid.UUID = OWNER, position: int = 0
) -> WorkboardCategory:
    return WorkboardCategory(
        id=uuid.uuid4(),
        owner_user_id=owner,
        name=name,
        name_key=name.casefold(),
        position=position,
    )


def _ticket(*, owner: uuid.UUID = OWNER, category_id: uuid.UUID | None = None) -> WorkboardTicket:
    return WorkboardTicket(
        id=uuid.uuid4(), owner_user_id=owner, title="Book the venue", category_id=category_id
    )


def _code(exc: BaseAPIException) -> str:
    return exc.detail if isinstance(exc.detail, str) else str(exc.detail)


@dataclass
class Harness:
    """The service under test, and the account fence it must take."""

    service: WorkboardCategoryService
    fence: AsyncMock


@pytest.fixture
def harness() -> Iterator[Harness]:
    with patch("src.domains.workboard.category_service.lock_peer_pair", AsyncMock()) as fence:
        service = WorkboardCategoryService(db=AsyncMock())
        service.repo = AsyncMock()
        service.repo.list_owned.return_value = []
        service.repo.list_visible.return_value = []
        service.repo.count_tickets.return_value = 0
        service.repo.ticket_counts.return_value = {}
        service.repo.create = AsyncMock(
            side_effect=lambda values: WorkboardCategory(id=uuid.uuid4(), **values)
        )
        yield Harness(service=service, fence=fence)


class TestNames:
    async def test_a_name_is_stored_trimmed_with_single_spaces(self, harness: Harness) -> None:
        row = await harness.service.create(_user(OWNER), CategoryCreate(name="  Home   works "))
        assert row.name == "Home works"

    @pytest.mark.parametrize("blank", ["", "   ", "\t\n"])
    async def test_a_blank_name_is_refused(self, harness: Harness, blank: str) -> None:
        with pytest.raises(BaseAPIException) as exc:
            await harness.service.create(_user(OWNER), CategoryCreate(name=blank))
        assert _code(exc.value) == WorkboardError.CATEGORY_NAME_REQUIRED.value

    async def test_the_bound_is_the_setting_never_a_literal(self, harness: Harness) -> None:
        limit = settings.workboard_category_name_max_chars
        await harness.service.create(_user(OWNER), CategoryCreate(name="x" * limit))
        with pytest.raises(BaseAPIException) as exc:
            await harness.service.create(_user(OWNER), CategoryCreate(name="x" * (limit + 1)))
        assert _code(exc.value) == WorkboardError.CATEGORY_NAME_TOO_LONG.value

    @pytest.mark.parametrize("spelling", ["maison", "MAISON", "Maïson", " Maison ", "Maïson"])
    async def test_two_spellings_of_one_name_are_one_category(
        self, harness: Harness, spelling: str
    ) -> None:
        """Folding decides identity: a second « Maison » would be a second lane
        nobody can tell from the first, and a name the assistant cannot resolve."""
        existing = _category("Maison")
        existing.name_key = "maison"
        harness.service.repo.list_owned.return_value = [existing]
        with pytest.raises(BaseAPIException) as exc:
            await harness.service.create(_user(OWNER), CategoryCreate(name=spelling))
        assert _code(exc.value) == WorkboardError.CATEGORY_NAME_TAKEN.value

    async def test_a_category_may_keep_its_own_name_when_edited(self, harness: Harness) -> None:
        existing = _category("Maison")
        existing.name_key = "maison"
        harness.service.repo.list_owned.return_value = [existing]
        row = await harness.service.update(_user(OWNER), existing.id, CategoryUpdate(name="MAISON"))
        assert row.name == "MAISON"


class TestCap:
    async def test_the_cap_is_the_setting_and_is_refused_at_it(self, harness: Harness) -> None:
        cap = settings.workboard_max_categories_per_user
        harness.service.repo.list_owned.return_value = [
            _category(f"c{index}", position=index) for index in range(cap)
        ]
        with pytest.raises(BaseAPIException) as exc:
            await harness.service.create(_user(OWNER), CategoryCreate(name="one too many"))
        assert _code(exc.value) == WorkboardError.TOO_MANY_CATEGORIES.value
        harness.service.repo.create.assert_not_awaited()

    async def test_one_below_the_cap_is_accepted(self, harness: Harness) -> None:
        cap = settings.workboard_max_categories_per_user
        harness.service.repo.list_owned.return_value = [
            _category(f"c{index}", position=index) for index in range(cap - 1)
        ]
        row = await harness.service.create(_user(OWNER), CategoryCreate(name="the last one"))
        assert row.position == cap - 1


class TestOrder:
    async def test_a_new_category_lands_last_by_default(self, harness: Harness) -> None:
        harness.service.repo.list_owned.return_value = [_category("a"), _category("b", position=1)]
        row = await harness.service.create(_user(OWNER), CategoryCreate(name="c"))
        assert row.position == 2
        harness.service.repo.renumber.assert_not_awaited()

    async def test_a_new_category_may_be_inserted_and_the_rest_shifts(
        self, harness: Harness
    ) -> None:
        first, second = _category("a"), _category("b", position=1)
        harness.service.repo.list_owned.return_value = [first, second]
        row = await harness.service.create(_user(OWNER), CategoryCreate(name="c", position=1))
        ordered = harness.service.repo.renumber.await_args.args[1]
        assert ordered == [first.id, row.id, second.id]

    async def test_a_move_past_the_end_is_clamped_never_refused(self, harness: Harness) -> None:
        first, second, third = (
            _category("a"),
            _category("b", position=1),
            _category("c", position=2),
        )
        harness.service.repo.list_owned.return_value = [first, second, third]
        row = await harness.service.update(_user(OWNER), first.id, CategoryUpdate(position=99))
        assert harness.service.repo.renumber.await_args.args[1] == [second.id, third.id, first.id]
        assert row.position == 2

    async def test_a_rename_alone_renumbers_nothing(self, harness: Harness) -> None:
        only = _category("a")
        harness.service.repo.list_owned.return_value = [only]
        await harness.service.update(_user(OWNER), only.id, CategoryUpdate(name="b"))
        harness.service.repo.renumber.assert_not_awaited()


class TestOwnership:
    async def test_somebody_elses_category_answers_like_one_that_does_not_exist(
        self, harness: Harness
    ) -> None:
        """A neutral 404: an id cannot be probed (the ticket's own rule)."""
        harness.service.repo.list_owned.return_value = [_category("mine")]
        with pytest.raises(ResourceNotFoundError):
            await harness.service.update(_user(OWNER), uuid.uuid4(), CategoryUpdate(name="x"))
        with pytest.raises(ResourceNotFoundError):
            await harness.service.delete(_user(OWNER), uuid.uuid4())

    async def test_every_write_takes_the_account_fence_first(self, harness: Harness) -> None:
        """Cap, uniqueness and order are read-then-write: two requests must not
        both read « 19 of 20 », nor a deletion race a ticket being filed."""
        actor = _user(OWNER)
        existing = _category("a")
        harness.service.repo.list_owned.return_value = [existing]
        await harness.service.create(actor, CategoryCreate(name="b"))
        await harness.service.update(actor, existing.id, CategoryUpdate(name="c"))
        await harness.service.delete(actor, existing.id)
        assert harness.fence.await_count == 3
        for call in harness.fence.await_args_list:
            assert call.args[1:] == (OWNER, OWNER)


class TestDelete:
    async def test_it_says_how_many_tickets_it_released_and_closes_the_gap(
        self, harness: Harness
    ) -> None:
        first, second, third = (
            _category("a"),
            _category("b", position=1),
            _category("c", position=2),
        )
        harness.service.repo.list_owned.return_value = [first, second, third]
        harness.service.repo.count_tickets.return_value = 4
        released = await harness.service.delete(_user(OWNER), second.id)
        assert released == 4
        harness.service.db.delete.assert_awaited_once_with(second)
        assert harness.service.repo.renumber.await_args.args[1] == [first.id, third.id]


class TestFilingATicket:
    async def test_nothing_asked_touches_nothing(self, harness: Harness) -> None:
        category = uuid.uuid4()
        ticket = _ticket(category_id=category)
        await harness.service.file(ticket, PEER, None, clear=False)
        assert ticket.category_id == category
        harness.service.repo.get_owned.assert_not_awaited()

    async def test_the_owner_files_under_one_of_their_own(self, harness: Harness) -> None:
        category = _category("Home")
        harness.service.repo.get_owned.return_value = category
        ticket = _ticket()
        await harness.service.file(ticket, OWNER, category.id, clear=False)
        assert ticket.category_id == category.id
        harness.service.repo.get_owned.assert_awaited_once_with(category.id, OWNER)

    async def test_the_owner_takes_a_ticket_out_of_its_category(self, harness: Harness) -> None:
        ticket = _ticket(category_id=uuid.uuid4())
        await harness.service.file(ticket, OWNER, None, clear=True)
        assert ticket.category_id is None

    @pytest.mark.parametrize("clear", [False, True])
    async def test_a_holder_cannot_refile_the_owners_ticket(
        self, harness: Harness, clear: bool
    ) -> None:
        """The category is the owner's word about the ticket, like its title."""
        original = uuid.uuid4()
        ticket = _ticket(category_id=original)
        with pytest.raises(BaseAPIException) as exc:
            await harness.service.file(ticket, PEER, None if clear else uuid.uuid4(), clear=clear)
        assert _code(exc.value) == WorkboardError.PEER_CANNOT_EDIT_FIELD.value
        assert ticket.category_id == original

    async def test_a_category_that_is_not_the_owners_is_refused_by_code(
        self, harness: Harness
    ) -> None:
        harness.service.repo.get_owned.return_value = None
        ticket = _ticket()
        with pytest.raises(BaseAPIException) as exc:
            await harness.service.file(ticket, OWNER, uuid.uuid4(), clear=False)
        assert _code(exc.value) == WorkboardError.CATEGORY_UNKNOWN.value
        assert ticket.category_id is None


class TestCreationCategory:
    async def test_an_explicit_category_must_be_the_owners(self, harness: Harness) -> None:
        harness.service.repo.get_owned.return_value = None
        with pytest.raises(BaseAPIException) as exc:
            await harness.service.creation_category(OWNER, uuid.uuid4(), None)
        assert _code(exc.value) == WorkboardError.CATEGORY_UNKNOWN.value

    async def test_a_step_is_born_in_its_parents_lane(self, harness: Harness) -> None:
        """A step landing in « to categorise », away from the ticket it is a
        step of, would undo the reading the lanes exist to give."""
        parent = _ticket(category_id=uuid.uuid4())
        assert await harness.service.creation_category(OWNER, None, parent) == parent.category_id

    async def test_an_explicit_category_wins_over_the_parents(self, harness: Harness) -> None:
        chosen = _category("Elsewhere")
        harness.service.repo.get_owned.return_value = chosen
        parent = _ticket(category_id=uuid.uuid4())
        assert await harness.service.creation_category(OWNER, chosen.id, parent) == chosen.id

    async def test_a_ticket_with_no_parent_and_no_category_is_not_filed(
        self, harness: Harness
    ) -> None:
        assert await harness.service.creation_category(OWNER, None, None) is None
        harness.service.repo.get_owned.assert_not_awaited()


class TestLanes:
    async def test_an_account_with_no_category_has_no_lane_and_pays_no_aggregate(
        self, harness: Harness
    ) -> None:
        """The board then draws exactly what it drew before categories existed."""
        assert await harness.service.lanes(_user(OWNER), BoardFilters()) == []
        harness.service.repo.lane_counts.assert_not_awaited()

    async def test_the_unfiled_lane_leads_then_the_readers_own_then_the_others(
        self, harness: Harness
    ) -> None:
        mine_first, mine_second = _category("Home"), _category("Work", position=1)
        theirs = _category("Shared", owner=PEER)
        harness.service.repo.list_visible.return_value = [mine_first, mine_second, theirs]
        harness.service.repo.lane_counts.return_value = {}
        lanes = await harness.service.lanes(_user(OWNER), BoardFilters())
        assert [lane.category_id for lane in lanes] == [
            None,
            mine_first.id,
            mine_second.id,
            theirs.id,
        ]
        assert lanes[0].name is None and lanes[0].owner_user_id is None
        assert lanes[3].owner_user_id == PEER

    async def test_every_lane_counts_every_column_exactly(self, harness: Harness) -> None:
        home = _category("Home")
        harness.service.repo.list_visible.return_value = [home]
        harness.service.repo.lane_counts.return_value = {
            (None, "todo"): 2,
            (home.id, "todo"): 3,
            (home.id, "done"): 1,
        }
        unfiled, lane = await harness.service.lanes(_user(OWNER), BoardFilters())
        assert set(lane.counts_by_status) == set(STATUS_ORDER), "a missing column reads as absent"
        assert lane.counts_by_status["todo"] == 3
        assert lane.counts_by_status["done"] == 1
        assert lane.counts_by_status["idea"] == 0
        assert unfiled.counts_by_status["todo"] == 2


class TestListing:
    async def test_the_caps_travel_with_the_list(self, harness: Harness) -> None:
        """A bound the form cannot read is a bound it walks into (ADR-184)."""
        listing = await harness.service.listing(_user(OWNER))
        assert listing.max_categories == settings.workboard_max_categories_per_user
        assert listing.name_max_chars == settings.workboard_category_name_max_chars
        assert listing.categories == []

    async def test_each_category_carries_its_exact_ticket_count(self, harness: Harness) -> None:
        home, work = _category("Home"), _category("Work", position=1)
        harness.service.repo.list_visible.return_value = [home, work]
        harness.service.repo.ticket_counts.return_value = {home.id: 5}
        listing = await harness.service.listing(_user(OWNER))
        assert [(row.name, row.ticket_count) for row in listing.categories] == [
            ("Home", 5),
            ("Work", 0),
        ]


class TestNamesOfTickets:
    """The names the hub, the dashboard and the assistant show beside a ticket."""

    async def test_tickets_filed_under_nothing_cost_no_query(self, harness: Harness) -> None:
        assert await harness.service.names_for(OWNER, [_ticket(), _ticket()]) == {}
        harness.service.repo.names.assert_not_awaited()

    async def test_each_category_is_asked_once_and_for_the_reader(self, harness: Harness) -> None:
        home = uuid.uuid4()
        harness.service.repo.names.return_value = {home: "Home"}
        names = await harness.service.names_for(
            OWNER, [_ticket(category_id=home), _ticket(category_id=home), _ticket()]
        )
        assert names == {home: "Home"}
        harness.service.repo.names.assert_awaited_once_with(OWNER, {home})

    async def test_a_category_that_is_gone_is_simply_not_named(self, harness: Harness) -> None:
        """Deleted between the two reads: the ticket shows no badge, never a stale name."""
        harness.service.repo.names.return_value = {}
        assert await harness.service.names_for(OWNER, [_ticket(category_id=uuid.uuid4())]) == {}


class TestACategoryNamedByItsName:
    """The assistant names a category the way the person does: by its name.

    Two questions, two sets. FILING a ticket reads the ACTOR's own categories
    — a name of somebody else's is not found, so no answer ever says whether
    another account has a category called that. NARROWING the board reads
    every lane on the reader's board, theirs or not.
    """

    async def test_filing_finds_one_of_the_actors_own_whatever_the_spelling(
        self, harness: Harness
    ) -> None:
        home = _category("Maison été")
        home.name_key = fold_name("Maison été")
        harness.service.repo.list_owned.return_value = [home, _category("Work", position=1)]

        assert await harness.service.own_named(OWNER, "  maison   ETE ") == home.id
        harness.service.repo.list_owned.assert_awaited_with(OWNER)

    @pytest.mark.parametrize("name", ["Garden", "", "   "])
    async def test_filing_under_a_name_the_actor_does_not_have_is_refused_by_code(
        self, harness: Harness, name: str
    ) -> None:
        harness.service.repo.list_owned.return_value = [_category("Home")]
        with pytest.raises(BaseAPIException) as exc:
            await harness.service.own_named(OWNER, name)
        assert _code(exc.value) == WorkboardError.CATEGORY_UNKNOWN.value

    async def test_narrowing_matches_every_lane_of_that_name_on_the_board(
        self, harness: Harness
    ) -> None:
        """Two people may both have a « Home »: the reader asked for both."""
        mine, theirs = _category("Home"), _category("home", owner=PEER)
        harness.service.repo.list_visible.return_value = [mine, _category("Work"), theirs]

        assert await harness.service.visible_named(OWNER, "HOME") == (mine.id, theirs.id)
        harness.service.repo.list_visible.assert_awaited_with(OWNER)

    async def test_narrowing_to_a_name_not_on_the_board_is_refused_never_an_empty_page(
        self, harness: Harness
    ) -> None:
        """« No ticket in Garden » and « no category Garden » are not one answer."""
        harness.service.repo.list_visible.return_value = [_category("Home")]
        with pytest.raises(BaseAPIException) as exc:
            await harness.service.visible_named(OWNER, "Garden")
        assert _code(exc.value) == WorkboardError.CATEGORY_UNKNOWN.value
