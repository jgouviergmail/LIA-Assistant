"""One row per turn, and a resumption is the SAME turn (ADR-263, lot 6).

The whole lot reduces to one statement, and only PostgreSQL can prove it: the
upsert that merges a resumed turn into the row its first segment wrote. A mock
would assert that the code calls SQLAlchemy; it cannot assert that
``GREATEST``, ``LEAST`` and ``COALESCE`` produce a row that still tells the
truth about a turn stopped for a confirmation and finished twenty minutes later.

The pointer semantics need the real thing too: ``ON DELETE SET NULL`` on two
foreign keys is what turns a deleted conversation into a dated TOMBSTONE
instead of a cascade that would erase the fact along with the words.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from src.domains.agents.effects.decision_repository import DecisionRepository
from src.domains.agents.effects.decisions import TurnDecision
from src.domains.agents.effects.models import AgentDecision, DecisionOutcome
from src.domains.conversations.models import Conversation, ConversationMessage
from src.domains.users.models import User

pytestmark = pytest.mark.integration

_START = datetime(2026, 9, 4, 10, 0, tzinfo=UTC)


@pytest.fixture
async def user(async_session: AsyncSession) -> User:
    """The account whose turns are under test."""
    row = User(
        email=f"decision-{uuid.uuid4().hex[:8]}@test.local",
        hashed_password="x",
        is_active=True,
        is_superuser=False,
        full_name="Decision Owner",
    )
    async_session.add(row)
    await async_session.flush()
    return row


@pytest.fixture
async def conversation(async_session: AsyncSession, user: User) -> Conversation:
    """A conversation the pointers can point at."""
    row = Conversation(user_id=user.id, title="Turn under test")
    async_session.add(row)
    await async_session.flush()
    return row


async def _message(
    session: AsyncSession, conversation: Conversation, *, role: str
) -> ConversationMessage:
    row = ConversationMessage(conversation_id=conversation.id, role=role, content=f"{role} text")
    session.add(row)
    await session.flush()
    return row


def _turn(user: User, run_id: str, **overrides: object) -> TurnDecision:
    base: dict[str, object] = {
        "run_id": run_id,
        "user_id": user.id,
        "thread_id": "thread-A",
        "source": "user",
        "execution_mode": "pipeline",
        "started_at": _START,
    }
    base.update(overrides)
    return TurnDecision(**base)  # type: ignore[arg-type]


async def _row(session: AsyncSession, run_id: str) -> AgentDecision:
    found = (
        await session.execute(select(AgentDecision).where(AgentDecision.run_id == run_id))
    ).scalar_one()
    await session.refresh(found)
    return found


class TestOneTurnOneRow:
    async def test_a_turn_is_written_once(self, async_session: AsyncSession, user: User) -> None:
        decision = _turn(user, "run-1")

        await DecisionRepository(async_session).record(
            decision, ended_at=_START + timedelta(seconds=3)
        )
        await async_session.flush()

        row = await _row(async_session, "run-1")
        assert row.segments == 1
        assert row.duration_ms == 3000
        assert row.outcome is DecisionOutcome.INTERRUPTED

    async def test_a_resumption_MERGES_rather_than_failing_or_duplicating(
        self, async_session: AsyncSession, user: User
    ) -> None:
        """A HITL resumption reuses the run id. An insert would fail on the
        unique constraint; dropping the constraint would file one turn as two."""
        repository = DecisionRepository(async_session)
        first = _turn(user, "run-1", route="planner")
        await repository.record(first, ended_at=_START + timedelta(seconds=4))
        await async_session.flush()

        resumed = _turn(
            user,
            "run-1",
            started_at=_START + timedelta(minutes=20),
            outcome=DecisionOutcome.ANSWERED,
        )
        await repository.record(resumed, ended_at=_START + timedelta(minutes=20, seconds=6))
        await async_session.flush()

        rows = (
            (
                await async_session.execute(
                    select(AgentDecision).where(AgentDecision.run_id == "run-1")
                )
            )
            .scalars()
            .all()
        )
        assert len(rows) == 1, "one turn was filed as two"

    async def test_a_resumed_turn_is_LEGIBLE_as_one(
        self, async_session: AsyncSession, user: User
    ) -> None:
        """Without ``segments`` an interrupted turn and a straight one look
        identical once resumed — and the interruption is the interesting half."""
        repository = DecisionRepository(async_session)
        await repository.record(_turn(user, "run-1"), ended_at=_START + timedelta(seconds=4))
        await async_session.flush()
        await repository.record(
            _turn(user, "run-1", started_at=_START + timedelta(minutes=20)),
            ended_at=_START + timedelta(minutes=20, seconds=6),
        )
        await async_session.flush()

        row = await _row(async_session, "run-1")
        assert row.segments == 2

    async def test_the_turn_began_when_it_BEGAN(
        self, async_session: AsyncSession, user: User
    ) -> None:
        repository = DecisionRepository(async_session)
        await repository.record(_turn(user, "run-1"), ended_at=_START + timedelta(seconds=4))
        await async_session.flush()
        await repository.record(
            _turn(user, "run-1", started_at=_START + timedelta(minutes=20)),
            ended_at=_START + timedelta(minutes=20, seconds=6),
        )
        await async_session.flush()

        row = await _row(async_session, "run-1")
        assert row.started_at == _START
        assert row.ended_at == _START + timedelta(minutes=20, seconds=6)

    async def test_the_duration_ACCUMULATES_and_never_counts_the_wait(
        self, async_session: AsyncSession, user: User
    ) -> None:
        """Twenty minutes of a human deciding is not twenty minutes of a turn
        running. Re-measuring from the wall clock would say otherwise."""
        repository = DecisionRepository(async_session)
        await repository.record(_turn(user, "run-1"), ended_at=_START + timedelta(seconds=4))
        await async_session.flush()
        await repository.record(
            _turn(user, "run-1", started_at=_START + timedelta(minutes=20)),
            ended_at=_START + timedelta(minutes=20, seconds=6),
        )
        await async_session.flush()

        row = await _row(async_session, "run-1")
        assert row.duration_ms == 10_000, "the wall clock leaked into the duration"

    async def test_the_LATEST_verdict_wins(self, async_session: AsyncSession, user: User) -> None:
        """It is the segment that saw how the turn actually ended."""
        repository = DecisionRepository(async_session)
        await repository.record(_turn(user, "run-1"), ended_at=_START + timedelta(seconds=4))
        await async_session.flush()
        await repository.record(
            _turn(
                user,
                "run-1",
                started_at=_START + timedelta(minutes=20),
                outcome=DecisionOutcome.ANSWERED,
            ),
            ended_at=_START + timedelta(minutes=20, seconds=6),
        )
        await async_session.flush()

        assert (await _row(async_session, "run-1")).outcome is DecisionOutcome.ANSWERED

    async def test_a_later_segment_never_BLANKS_what_an_earlier_one_established(
        self, async_session: AsyncSession, user: User, conversation: Conversation
    ) -> None:
        """A resumption does not re-archive the request, so it carries no
        pointer — and must not erase the one the first segment recorded."""
        asked = await _message(async_session, conversation, role="user")
        repository = DecisionRepository(async_session)
        await repository.record(
            _turn(user, "run-1", route="planner", plan_step_count=3, request_message_id=asked.id),
            ended_at=_START + timedelta(seconds=4),
        )
        await async_session.flush()
        await repository.record(
            _turn(user, "run-1", started_at=_START + timedelta(minutes=20)),
            ended_at=_START + timedelta(minutes=20, seconds=6),
        )
        await async_session.flush()

        row = await _row(async_session, "run-1")
        assert row.route == "planner"
        assert row.plan_step_count == 3
        assert row.request_message_id == asked.id


class TestItPointsAndLeavesATombstone:
    async def test_the_pointers_resolve_to_the_real_messages(
        self, async_session: AsyncSession, user: User, conversation: Conversation
    ) -> None:
        asked = await _message(async_session, conversation, role="user")
        answered = await _message(async_session, conversation, role="assistant")

        await DecisionRepository(async_session).record(
            _turn(
                user,
                "run-1",
                request_message_id=asked.id,
                response_message_id=answered.id,
                outcome=DecisionOutcome.ANSWERED,
            ),
            ended_at=_START + timedelta(seconds=2),
        )
        await async_session.flush()

        row = await _row(async_session, "run-1")
        assert (row.request_message_id, row.response_message_id) == (asked.id, answered.id)

    async def test_deleting_the_conversation_leaves_the_TURN(
        self, async_session: AsyncSession, user: User, conversation: Conversation
    ) -> None:
        """The turn happened. Deleting the words must remove the words — never
        the fact, and never resurrect them either (ADR-201 doctrine)."""
        asked = await _message(async_session, conversation, role="user")
        await DecisionRepository(async_session).record(
            _turn(user, "run-1", request_message_id=asked.id),
            ended_at=_START + timedelta(seconds=2),
        )
        await async_session.flush()

        await async_session.execute(delete(Conversation).where(Conversation.id == conversation.id))
        await async_session.flush()

        row = await _row(async_session, "run-1")
        assert row.request_message_id is None, "the pointer survived its target"
        assert row.run_id == "run-1", "the turn was cascaded away with the words"

    async def test_deleting_the_account_removes_the_turn(
        self, async_session: AsyncSession, user: User
    ) -> None:
        await DecisionRepository(async_session).record(
            _turn(user, "run-1"), ended_at=_START + timedelta(seconds=2)
        )
        await async_session.flush()

        await async_session.execute(delete(User).where(User.id == user.id))
        await async_session.flush()

        rows = (
            (
                await async_session.execute(
                    select(AgentDecision).where(AgentDecision.run_id == "run-1")
                )
            )
            .scalars()
            .all()
        )
        assert rows == []


class TestTheJournalRead:
    async def test_the_total_is_EXACT_over_the_filtered_set(
        self, async_session: AsyncSession, user: User
    ) -> None:
        """A count shown to a user is exact or it does not exist (ADR-185)."""
        repository = DecisionRepository(async_session)
        for index in range(5):
            await repository.record(
                _turn(user, f"run-{index}", started_at=_START + timedelta(minutes=index)),
                ended_at=_START + timedelta(minutes=index, seconds=1),
            )
        await async_session.flush()

        rows, total = await repository.list_for_user(user.id, limit=2, offset=0)

        assert len(rows) == 2
        assert total == 5, "the total came from the page length"

    async def test_the_period_filter_narrows_the_total_too(
        self, async_session: AsyncSession, user: User
    ) -> None:
        """A global total above a filtered list describes a set the reader
        cannot see — the same defect wearing a different hat."""
        repository = DecisionRepository(async_session)
        for index in range(5):
            await repository.record(
                _turn(user, f"run-{index}", started_at=_START + timedelta(minutes=index)),
                ended_at=_START + timedelta(minutes=index, seconds=1),
            )
        await async_session.flush()

        _, total = await repository.list_for_user(
            user.id, limit=10, offset=0, since=_START + timedelta(minutes=3)
        )

        assert total == 2

    async def test_the_newest_turn_comes_first(
        self, async_session: AsyncSession, user: User
    ) -> None:
        repository = DecisionRepository(async_session)
        for index in range(3):
            await repository.record(
                _turn(user, f"run-{index}", started_at=_START + timedelta(minutes=index)),
                ended_at=_START + timedelta(minutes=index, seconds=1),
            )
        await async_session.flush()

        rows, _ = await repository.list_for_user(user.id, limit=10, offset=0)

        assert [row.run_id for row in rows] == ["run-2", "run-1", "run-0"]

    async def test_a_turn_of_another_account_is_invisible(
        self, async_session: AsyncSession, user: User
    ) -> None:
        other = User(
            email=f"other-{uuid.uuid4().hex[:8]}@test.local",
            hashed_password="x",
            is_active=True,
            is_superuser=False,
            full_name="Other",
        )
        async_session.add(other)
        await async_session.flush()
        repository = DecisionRepository(async_session)
        await repository.record(_turn(other, "run-x"), ended_at=_START + timedelta(seconds=1))
        await async_session.flush()

        rows, total = await repository.list_for_user(user.id, limit=10, offset=0)

        assert (rows, total) == ([], 0)


class TestTheTechnicalExportOfTurns:
    """The third register, read end to end.

    A branch added to a dispatch and never executed is a branch that works
    until the day someone opens it. This drives the real repository, the real
    spec and the real renderer.
    """

    async def test_a_turn_exports_pseudonymised_and_content_free(
        self, async_session: AsyncSession, user: User, conversation: Conversation
    ) -> None:
        from src.domains.agents.effects.technical_export import (
            DECISIONS_SPEC,
            pseudonymise,
            technical_row,
        )

        asked = await _message(async_session, conversation, role="user")
        await DecisionRepository(async_session).record(
            _turn(
                user,
                "run-1",
                route="planner",
                plan_step_count=3,
                request_message_id=asked.id,
                outcome=DecisionOutcome.ANSWERED,
            ),
            ended_at=_START + timedelta(seconds=2),
        )
        await async_session.flush()

        rows = await DecisionRepository(async_session).list_for_export(
            since=None, until=None, user_ids=[user.id], limit=100
        )
        exported = technical_row(rows[0], DECISIONS_SPEC)

        assert exported["route"] == "planner"
        assert exported["plan_step_count"] == 3
        assert exported["outcome"] == "answered"
        assert exported["user"] == pseudonymise(user.id)
        assert "user_id" not in exported, "the raw account id left the instance"
        assert exported["run_id"] != "run-1", "a correlation id left in the clear"
        assert exported["request_message_id"] != str(asked.id)

    async def test_the_period_and_account_filters_are_the_ones_it_HONOURS(
        self, async_session: AsyncSession, user: User
    ) -> None:
        repository = DecisionRepository(async_session)
        for index in range(4):
            await repository.record(
                _turn(user, f"run-{index}", started_at=_START + timedelta(minutes=index)),
                ended_at=_START + timedelta(minutes=index, seconds=1),
            )
        await async_session.flush()

        window = await repository.list_for_export(
            since=_START + timedelta(minutes=1),
            until=_START + timedelta(minutes=3),
            user_ids=[user.id],
            limit=100,
        )

        assert [row.run_id for row in window] == ["run-1", "run-2"]

    async def test_the_export_reads_OLDEST_first(
        self, async_session: AsyncSession, user: User
    ) -> None:
        """A history is read forward; the journal, backwards. Two orders, and
        the export must not borrow the journal's."""
        repository = DecisionRepository(async_session)
        for index in range(3):
            await repository.record(
                _turn(user, f"run-{index}", started_at=_START + timedelta(minutes=index)),
                ended_at=_START + timedelta(minutes=index, seconds=1),
            )
        await async_session.flush()

        rows = await repository.list_for_export(
            since=None, until=None, user_ids=[user.id], limit=100
        )

        assert [row.run_id for row in rows] == ["run-0", "run-1", "run-2"]

    async def test_the_dispatch_actually_reaches_the_decision_repository(
        self, async_session: AsyncSession, user: User
    ) -> None:
        """The branch, from the route's own value object."""
        from src.domains.agents.effects.technical_reads import TechnicalQuery, read_register

        await DecisionRepository(async_session).record(
            _turn(user, "run-1"), ended_at=_START + timedelta(seconds=1)
        )
        await async_session.flush()

        rows = await read_register(
            async_session,
            TechnicalQuery(
                register="decisions",
                since=None,
                until=None,
                user_ids=[user.id],
                tool_name="ignored_here",
                mutation_policy=None,
                status=None,
                source=None,
                execution_mode=None,
            ),
            100,
        )

        assert [row.run_id for row in rows] == ["run-1"]


class TestTheStopReasonMergesTheOtherWay:
    """The reason a turn stopped is the ONE field a later segment must blank.

    Every pointer uses ``COALESCE(new, existing)`` so a resumption that learned
    nothing cannot erase what the first segment established. The stop reason is
    deliberately the opposite: a turn that was resumed and then ran to its end
    no longer stopped short, and keeping the first segment's reason would leave
    the register saying it did.
    """

    async def test_a_resumption_that_ENDED_clears_the_reason(
        self, async_session: AsyncSession, user: User
    ) -> None:
        repository = DecisionRepository(async_session)
        await repository.record(
            _turn(user, "run-1", stop_reason="compute_budget"),
            ended_at=_START + timedelta(seconds=4),
        )
        await async_session.flush()

        await repository.record(
            _turn(
                user,
                "run-1",
                started_at=_START + timedelta(minutes=20),
                outcome=DecisionOutcome.ANSWERED,
            ),
            ended_at=_START + timedelta(minutes=20, seconds=3),
        )
        await async_session.flush()

        row = await _row(async_session, "run-1")
        assert row.stop_reason is None, "the turn still reads as stopped short"
        assert row.outcome is DecisionOutcome.ANSWERED

    async def test_a_resumption_that_stopped_AGAIN_says_so(
        self, async_session: AsyncSession, user: User
    ) -> None:
        repository = DecisionRepository(async_session)
        await repository.record(
            _turn(user, "run-1", stop_reason="max_iterations"),
            ended_at=_START + timedelta(seconds=4),
        )
        await async_session.flush()

        await repository.record(
            _turn(
                user,
                "run-1",
                started_at=_START + timedelta(minutes=20),
                stop_reason="tool_budget",
            ),
            ended_at=_START + timedelta(minutes=20, seconds=3),
        )
        await async_session.flush()

        row = await _row(async_session, "run-1")
        assert row.stop_reason == "tool_budget", "the LATEST segment saw how it ended"
        assert row.segments == 2

    async def test_a_straight_turn_has_none(self, async_session: AsyncSession, user: User) -> None:
        await DecisionRepository(async_session).record(
            _turn(user, "run-1", outcome=DecisionOutcome.ANSWERED),
            ended_at=_START + timedelta(seconds=2),
        )
        await async_session.flush()

        assert (await _row(async_session, "run-1")).stop_reason is None
