"""The ticket tools and the categories of a board, against a real server (ADR-276).

What a stubbed service cannot prove, and what is checked here:

- a ticket the assistant creates « in Home » is filed under Home once — and
  only once — the person has confirmed, and a step is born in its ticket's lane
  without failing the executor's own field-by-field verification;
- a category the user does not have is REFUSED before anything is proposed: no
  tool creates a category by naming one;
- a holder who names a category learns nothing about the owner's: the refusal
  is the same whether or not the owner has one called that;
- a comment and a deletion the workboard refuses say WHICH refusal it is — two
  tickets under that title, a ticket that is not the caller's to delete — by
  its stable code, and write nothing;
- the readers name each ticket's category, narrow to a lane by its name and
  count every lane exactly — and publish nothing once the authority is gone.
"""

from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from datetime import UTC, datetime
from typing import Any
from unittest.mock import AsyncMock, patch
from uuid import uuid4

import pytest
from langgraph.store.memory import InMemoryStore
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.config import settings
from src.domains.agents.application.draft_execution import execute_application_action_draft
from src.domains.agents.application.draft_models import ApplicationActionDraftContent
from src.domains.agents.services import draft_executor
from src.domains.agents.tools import workboard_tools
from src.domains.agents.workboard.category_manifest import categories_managed_from
from src.domains.peers.models import PeerConnection, PeerConnectionStatus, canonical_pair
from src.domains.users.models import User
from src.domains.workboard.category_service import WorkboardCategoryService
from src.domains.workboard.constants import WorkboardError
from src.domains.workboard.models import WorkboardComment, WorkboardTicket
from src.domains.workboard.schemas import CategoryCreate, CategoryRow, TicketCreate
from src.domains.workboard.service import WorkboardService
from tests.helpers.runtime_context import make_tool_runtime
from tests.integration.application_runtime_context import installed_runtime_context

pytestmark = [pytest.mark.integration, pytest.mark.usefixtures("agent_registry")]

THREAD = "workboard-category-tools"


@pytest.fixture(autouse=True)
def board_on(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(settings, "workboard_enabled", True)
    monkeypatch.setattr(settings, "peers_enabled", True, raising=False)


@pytest.fixture
def sessions(async_session: AsyncSession, monkeypatch: pytest.MonkeyPatch) -> None:
    """Every door the tools and the confirmed executor open leads to the test session."""

    @asynccontextmanager
    async def committing() -> AsyncIterator[AsyncSession]:
        try:
            yield async_session
            await async_session.commit()
        except BaseException:
            await async_session.rollback()
            raise

    @asynccontextmanager
    async def reading() -> AsyncIterator[AsyncSession]:
        yield async_session

    for module in (
        "command_service",
        "draft_execution",
        "workboard_create_editing",
        "workboard_update_editing",
    ):
        monkeypatch.setattr(f"src.domains.agents.application.{module}.get_db_context", committing)
    monkeypatch.setattr("src.infrastructure.database.session.get_db_context", committing)
    for tool in ("workboard_creation_tool", "workboard_update_tool"):
        monkeypatch.setattr(f"src.domains.agents.tools.{tool}.get_db_context", committing)
        monkeypatch.setattr(
            f"src.domains.agents.tools.{tool}.get_user_preferences",
            AsyncMock(return_value=("Europe/Paris", "fr", "fr-FR")),
        )
    for tool in ("workboard_comment_tool", "workboard_delete_tool"):
        monkeypatch.setattr(f"src.domains.agents.tools.{tool}.get_db_context", committing)
    monkeypatch.setattr(workboard_tools, "get_db_context", reading)


async def _category(session: AsyncSession, actor: User, name: str) -> CategoryRow:
    row = await WorkboardCategoryService(session).create(actor, CategoryCreate(name=name))
    await session.commit()
    return row


async def _ticket(session: AsyncSession, actor: User, **fields: Any) -> WorkboardTicket:
    ticket = await WorkboardService(session).create(actor, TicketCreate(**fields))
    await session.commit()
    return ticket


async def _peer_of(session: AsyncSession, user: User) -> User:
    """Another account, joined to ``user`` by an ACCEPTED connection."""
    peer = User(id=uuid4(), email=f"category-peer-{uuid4()}@example.test", is_active=True)
    session.add(peer)
    await session.flush()
    lo, hi = canonical_pair(peer.id, user.id)
    session.add(
        PeerConnection(
            user_a_id=lo,
            user_b_id=hi,
            requested_by_id=peer.id,
            status=PeerConnectionStatus.ACCEPTED.value,
            requested_at=datetime.now(UTC),
            responded_at=datetime.now(UTC),
        )
    )
    await session.commit()
    return peer


def _runtime(user_id: Any, **context: Any) -> Any:
    return make_tool_runtime(user_id=user_id, store=InMemoryStore(), **context)


async def _confirm(proposal: Any) -> dict[str, Any]:
    """Confirm a proposal the way the chat does, and hand back what it showed."""
    assert proposal.success and proposal.metadata["requires_confirmation"], proposal.model_dump()
    item = next(iter(proposal.registry_updates.values()))
    draft = ApplicationActionDraftContent.model_validate(item.payload["content"])
    with patch.dict(draft_executor.EXECUTOR_REGISTRY):
        draft_executor.register_executor("application_action", execute_application_action_draft)
        result = await draft_executor._execute_confirmed_draft(
            {
                "draft_id": item.id,
                "draft_type": "application_action",
                "draft_content": draft.model_dump(mode="json"),
            },
            {"configurable": {"thread_id": THREAD}},
            THREAD,
            "fr",
        )
    assert result.success, result.to_agent_result()
    return draft.before


class TestFilingFromTheChat:
    async def test_a_ticket_is_created_in_the_category_named_once_confirmed(
        self, async_session: AsyncSession, test_user: User, sessions: None
    ) -> None:
        owner = test_user.id
        home = await _category(async_session, test_user, "Maison été")
        with installed_runtime_context(
            user_id=owner, deps=object(), side_channel_queue=asyncio.Queue()
        ):
            # The name as a person says it: other case, no accent, loose spacing.
            proposal = await workboard_tools.create_ticket_tool.coroutine(
                title="Paint the hall", category="  maison ETE ", runtime=_runtime(owner)
            )
            shown = await _confirm(proposal)

        # The card named the lane; the row is filed under it.
        assert shown["workboard_create"]["category_name"] == "Maison été"
        stored = await async_session.scalar(
            select(WorkboardTicket)
            .where(WorkboardTicket.owner_user_id == owner)
            .execution_options(populate_existing=True)
        )
        assert stored is not None and stored.category_id == home.id

    async def test_a_step_is_born_in_its_tickets_lane_and_passes_the_executors_own_check(
        self, async_session: AsyncSession, test_user: User, sessions: None
    ) -> None:
        """The executor compares every requested field to the stored row: an
        inherited lane the request did not carry would fail it."""
        owner = test_user.id
        home = await _category(async_session, test_user, "Home")
        parent = await _ticket(async_session, test_user, title="Renovation", category_id=home.id)
        parent_id = parent.id
        with installed_runtime_context(
            user_id=owner, deps=object(), side_channel_queue=asyncio.Queue()
        ):
            proposal = await workboard_tools.create_ticket_tool.coroutine(
                title="Buy paint", parent_ticket="Renovation", runtime=_runtime(owner)
            )
            shown = await _confirm(proposal)

        assert shown["workboard_create"]["category_name"] == "Home"
        steps = (
            await async_session.scalars(
                select(WorkboardTicket)
                .where(WorkboardTicket.parent_id == parent_id)
                .execution_options(populate_existing=True)
            )
        ).all()
        assert [step.category_id for step in steps] == [home.id]

    async def test_naming_a_category_the_user_does_not_have_proposes_nothing(
        self, async_session: AsyncSession, test_user: User, sessions: None
    ) -> None:
        """No tool creates a category by naming one."""
        owner = test_user.id
        await _category(async_session, test_user, "Home")
        with installed_runtime_context(
            user_id=owner, deps=object(), side_channel_queue=asyncio.Queue()
        ):
            result = await workboard_tools.create_ticket_tool.coroutine(
                title="Plant tomatoes", category="Garden", runtime=_runtime(owner)
            )

        assert result.success is False and not result.registry_updates
        assert result.metadata["workboard_error"] == WorkboardError.CATEGORY_UNKNOWN.value
        assert await WorkboardService(async_session).repo.count_owned(owner) == 0
        # By id: the refused proposal rolled the session back, which expires
        # the fixture's own row.
        kept = await WorkboardCategoryService(async_session).repo.list_owned(owner)
        assert [row.name for row in kept] == ["Home"]

    async def test_a_ticket_is_refiled_then_taken_out_of_its_category(
        self, async_session: AsyncSession, test_user: User, sessions: None
    ) -> None:
        owner = test_user.id
        home = await _category(async_session, test_user, "Home")
        ticket = await _ticket(async_session, test_user, title="Refile me")
        identity = ticket.id
        with installed_runtime_context(
            user_id=owner, deps=object(), side_channel_queue=asyncio.Queue()
        ):
            shown = await _confirm(
                await workboard_tools.update_ticket_tool.coroutine(
                    ticket="Refile me", category="home", runtime=_runtime(owner)
                )
            )
            assert shown["workboard_update"]["category_name"] == "Home"
            stored = await async_session.get(WorkboardTicket, identity, populate_existing=True)
            assert stored is not None and stored.category_id == home.id

            await _confirm(
                await workboard_tools.update_ticket_tool.coroutine(
                    ticket="Refile me", clear_category=True, runtime=_runtime(owner)
                )
            )
        stored = await async_session.get(WorkboardTicket, identity, populate_existing=True)
        assert stored is not None and stored.category_id is None

    async def test_a_holder_learns_nothing_about_the_owners_categories(
        self, async_session: AsyncSession, test_user: User, sessions: None
    ) -> None:
        """The same refusal whether or not the OWNER has a category of that
        name: it is read among the holder's own, where it does not exist."""
        holder = test_user.id
        owner = await _peer_of(async_session, test_user)
        home = await _category(async_session, owner, "Home")
        await _category(async_session, owner, "Private plans")
        ticket = await WorkboardService(async_session, assignment_notices=[]).create(
            owner, TicketCreate(title="Held ticket", category_id=home.id, assignee_user_id=holder)
        )
        identity, lane = ticket.id, home.id
        await async_session.commit()

        refusals = []
        with installed_runtime_context(
            user_id=holder, deps=object(), side_channel_queue=asyncio.Queue()
        ):
            for name in ("Private plans", "Nobody has this one"):
                result = await workboard_tools.update_ticket_tool.coroutine(
                    ticket=str(identity), category=name, runtime=_runtime(holder)
                )
                assert result.success is False and not result.registry_updates
                refusals.append((result.error_code, result.message, result.metadata))

        assert refusals[0] == refusals[1], "an existing name must not read differently"
        # …and the refusal says what it is: the model is told the name matches
        # no category, by the workboard's stable code, not by a mute sentence.
        assert refusals[0][:2] == ("CONSTRAINT_VIOLATION", WorkboardError.CATEGORY_UNKNOWN.value)
        stored = await async_session.get(WorkboardTicket, identity, populate_existing=True)
        assert stored is not None and stored.category_id == lane

    async def test_a_holder_naming_their_own_category_is_told_the_ticket_is_not_theirs(
        self, async_session: AsyncSession, test_user: User, sessions: None
    ) -> None:
        """The name resolves — it is the holder's own — and the SOURCE refuses:
        another refusal, and the model must be able to tell the two apart."""
        holder = test_user.id
        owner = await _peer_of(async_session, test_user)
        home = await _category(async_session, owner, "Home")
        await _category(async_session, test_user, "Mine")
        ticket = await WorkboardService(async_session, assignment_notices=[]).create(
            owner, TicketCreate(title="Held ticket", category_id=home.id, assignee_user_id=holder)
        )
        identity, lane = ticket.id, home.id
        await async_session.commit()

        with installed_runtime_context(
            user_id=holder, deps=object(), side_channel_queue=asyncio.Queue()
        ):
            result = await workboard_tools.update_ticket_tool.coroutine(
                ticket=str(identity), category="mine", runtime=_runtime(holder)
            )

        assert result.success is False and not result.registry_updates
        assert (result.error_code, result.message) == (
            "CONSTRAINT_VIOLATION",
            WorkboardError.PEER_CANNOT_EDIT_FIELD.value,
        )
        stored = await async_session.get(WorkboardTicket, identity, populate_existing=True)
        assert stored is not None and stored.category_id == lane


class TestACommentAndADeletionSayWhichRefusal:
    """The shared preparation answers a refused validation with one sentence
    that names no cause; a refusal of the workboard itself travels by its code."""

    async def test_two_tickets_under_one_title_are_said_ambiguous_and_nothing_is_written(
        self, async_session: AsyncSession, test_user: User, sessions: None
    ) -> None:
        # Read before the refusals: each one rolls the session back, and an
        # expired row cannot be read again outside a greenlet.
        me = test_user.id
        first = await _ticket(async_session, test_user, title="Call the plumber")
        second = await _ticket(async_session, test_user, title="Call the plumber")
        identities = (first.id, second.id)

        with installed_runtime_context(
            user_id=me, deps=object(), side_channel_queue=asyncio.Queue()
        ):
            commented = await workboard_tools.comment_ticket_tool.coroutine(
                ticket="call the plumber", body="Done", runtime=_runtime(me)
            )
            deleted = await workboard_tools.delete_ticket_tool.coroutine(
                ticket="call the plumber", runtime=_runtime(me)
            )

        for result in (commented, deleted):
            assert result.success is False and not result.registry_updates
            assert (result.error_code, result.message) == (
                "CONSTRAINT_VIOLATION",
                WorkboardError.AMBIGUOUS_REFERENCE.value,
            )
        kept = (
            await async_session.scalars(
                select(WorkboardTicket.id).where(WorkboardTicket.id.in_(identities))
            )
        ).all()
        assert sorted(kept) == sorted(identities)
        assert (
            await async_session.scalar(
                select(func.count(WorkboardComment.id)).where(
                    WorkboardComment.ticket_id.in_(identities)
                )
            )
        ) == 0

    async def test_a_holder_asking_to_delete_is_told_the_ticket_is_not_theirs_to_delete(
        self, async_session: AsyncSession, test_user: User, sessions: None
    ) -> None:
        holder = test_user.id
        owner = await _peer_of(async_session, test_user)
        ticket = await WorkboardService(async_session, assignment_notices=[]).create(
            owner, TicketCreate(title="Held ticket", assignee_user_id=holder)
        )
        identity = ticket.id
        await async_session.commit()

        with installed_runtime_context(
            user_id=holder, deps=object(), side_channel_queue=asyncio.Queue()
        ):
            result = await workboard_tools.delete_ticket_tool.coroutine(
                ticket=str(identity), runtime=_runtime(holder)
            )

        assert result.success is False and not result.registry_updates
        assert (result.error_code, result.message) == (
            "CONSTRAINT_VIOLATION",
            WorkboardError.PEER_CANNOT_DELETE.value,
        )
        assert (
            await async_session.get(WorkboardTicket, identity, populate_existing=True) is not None
        )


class TestReadingFromTheChat:
    async def test_the_listing_names_each_category_and_narrows_to_a_lane_by_name(
        self, async_session: AsyncSession, test_user: User, sessions: None
    ) -> None:
        owner = test_user.id
        home = await _category(async_session, test_user, "Home")
        await _ticket(async_session, test_user, title="Filed", category_id=home.id)
        await _ticket(async_session, test_user, title="Loose")
        runtime = {"runtime": _runtime(owner)}

        everything = await workboard_tools.list_tickets_tool.coroutine(**runtime)
        assert {row["title"]: row["category"] for row in everything.structured_data["tickets"]} == {
            "Filed": "Home",
            "Loose": None,
        }

        narrowed = await workboard_tools.list_tickets_tool.coroutine(category="HOME", **runtime)
        assert [row["title"] for row in narrowed.structured_data["tickets"]] == ["Filed"]
        assert narrowed.structured_data["total"] == 1

        unfiled = await workboard_tools.list_tickets_tool.coroutine(uncategorized=True, **runtime)
        assert [row["title"] for row in unfiled.structured_data["tickets"]] == ["Loose"]

        both = await workboard_tools.list_tickets_tool.coroutine(
            category="home", uncategorized=True, **runtime
        )
        assert both.structured_data["total"] == 2

        unknown = await workboard_tools.list_tickets_tool.coroutine(category="Garden", **runtime)
        assert unknown.success is False and not unknown.structured_data
        assert unknown.metadata["workboard_error"] == WorkboardError.CATEGORY_UNKNOWN.value

    async def test_one_ticket_is_read_with_its_category_and_its_steps_theirs(
        self, async_session: AsyncSession, test_user: User, sessions: None
    ) -> None:
        owner = test_user.id
        home = await _category(async_session, test_user, "Home")
        work = await _category(async_session, test_user, "Work")
        parent = await _ticket(async_session, test_user, title="Renovation", category_id=home.id)
        await _ticket(
            async_session,
            test_user,
            title="Call the bank",
            parent_id=parent.id,
            category_id=work.id,
        )

        result = await workboard_tools.get_ticket_tool.coroutine(
            ticket="Renovation", runtime=_runtime(owner)
        )

        assert result.structured_data["ticket"]["category"] == "Home"
        assert [(row["title"], row["category"]) for row in result.structured_data["children"]] == [
            ("Call the bank", "Work")
        ]

    async def test_the_categories_are_listed_with_exact_counts_and_whose_they_are(
        self, async_session: AsyncSession, test_user: User, sessions: None
    ) -> None:
        reader = test_user.id
        owner = await _peer_of(async_session, test_user)
        home = await _category(async_session, test_user, "Home")
        await _category(async_session, test_user, "Work")
        site = await _category(async_session, owner, "Site")
        await _category(async_session, owner, "Private plans")
        await _ticket(async_session, test_user, title="A", category_id=home.id)
        await _ticket(async_session, test_user, title="B", category_id=home.id, status="done")
        await _ticket(async_session, test_user, title="C")
        await WorkboardService(async_session, assignment_notices=[]).create(
            owner, TicketCreate(title="Held", category_id=site.id, assignee_user_id=reader)
        )
        await async_session.commit()

        # The turn runs in German: the tool reads the language from its
        # runtime, and the place is named as a German screen shows it.
        result = await workboard_tools.list_ticket_categories_tool.coroutine(
            runtime=_runtime(reader, language="de")
        )

        assert result.success, result.model_dump()
        assert result.structured_data == {
            "categories": [
                {"name": "Home", "mine": True, "tickets": 2},
                {"name": "Work", "mine": True, "tickets": 0},
                # The lane of the ticket held for somebody else — and nothing
                # else of that person's vocabulary.
                {"name": "Site", "mine": False, "tickets": 1},
            ],
            "managed_from": categories_managed_from("de"),
            "unfiled_tickets": 1,
        }
        assert "the 'Kategorien' button" in result.structured_data["managed_from"]

    async def test_a_board_with_no_category_answers_an_empty_list_and_no_count(
        self, async_session: AsyncSession, test_user: User, sessions: None
    ) -> None:
        await _ticket(async_session, test_user, title="Alone")

        result = await workboard_tools.list_ticket_categories_tool.coroutine(
            runtime=_runtime(test_user.id, language="es")
        )

        assert result.success and result.structured_data == {
            "categories": [],
            "managed_from": categories_managed_from("es"),
        }

    @pytest.mark.parametrize("scenario", ["disabled", "late_disabled"])
    async def test_the_category_reader_obeys_the_application_switch(
        self,
        async_session: AsyncSession,
        test_user: User,
        sessions: None,
        monkeypatch: pytest.MonkeyPatch,
        scenario: str,
    ) -> None:
        """Like the two older readers: off, it reads nothing; switched off
        WHILE it read, it publishes nothing."""
        await _category(async_session, test_user, "Home")
        if scenario == "disabled":
            monkeypatch.setattr(settings, "application_tools_enabled", False)
        else:
            source = WorkboardCategoryService.lanes

            async def fetched(service: Any, *args: Any, **kwargs: Any) -> Any:
                lanes = await source(service, *args, **kwargs)
                monkeypatch.setattr(settings, "application_tools_enabled", False)
                return lanes

            monkeypatch.setattr(WorkboardCategoryService, "lanes", fetched)

        result = await workboard_tools.list_ticket_categories_tool.coroutine(
            runtime=_runtime(test_user.id)
        )

        assert result.success is False and result.error_code == "CAPABILITY_DISABLED"
        assert not result.structured_data and not result.registry_updates
