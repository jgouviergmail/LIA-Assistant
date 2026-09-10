"""Claiming, settling and pricing a run against a real server (ADR-276).

Four things only PostgreSQL can answer, and each one is a defect class the
statement-shape tests cannot see:

- **two workers, one ticket.** ``FOR UPDATE SKIP LOCKED`` is a property of the
  server's lock manager; a compiled statement only says we asked for it. The
  race here runs two INDEPENDENT connections — the savepoint-isolated
  ``async_session`` cannot show it, since neither side would see the other's
  committed rows.
- **a settle that lost its ticket.** The person who moved it mid-run wins, and
  the late settle must match NOTHING rather than drag the ticket back to a
  column they left.
- **a release gives the run back.** A quota refusal is not a run: the lifetime
  budget must come out of it unchanged, or a fortnight of refusals silently
  exhausts a ticket.
- **the retention deletes the right rows.** The predicate walks a JSON value
  into another table's rows; a typo there deletes nothing for ever, or worse,
  deletes somebody's conversation.
"""

from __future__ import annotations

import asyncio
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from typing import Any
from uuid import UUID, uuid4

import pytest
import pytest_asyncio
from sqlalchemy import delete, func, select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from src.domains.chat.models import MessageTokenSummary, TokenUsageLog
from src.domains.conversations.models import Conversation, ConversationMessage
from src.domains.users.models import User
from src.domains.workboard.constants import (
    RUN_ORIGIN_KIND,
    AssigneeKind,
    RunError,
    RunOutcome,
    TicketPriority,
    TicketStatus,
)
from src.domains.workboard.models import WorkboardTicket
from src.domains.workboard.repository import RunUsage, WorkboardRepository

pytestmark = pytest.mark.integration

NOW = datetime(2026, 9, 9, 12, 0, tzinfo=UTC)


def _ticket(owner_id: UUID, **overrides: Any) -> WorkboardTicket:
    """A ticket LIA may run, unless an override says otherwise."""
    values: dict[str, Any] = {
        "owner_user_id": owner_id,
        "title": "Book the venue",
        "description": "Find a room for twelve on the 20th.",
        "status": TicketStatus.TODO.value,
        "priority": TicketPriority.MEDIUM.value,
        "assignee_kind": AssigneeKind.LIA.value,
        "assignee_user_id": None,
        "position": 0,
        "created_by": "user",
        "status_changed_at": NOW,
        "run_attempts": 0,
        "run_count": 0,
        "nudge_count": 0,
    }
    values.update(overrides)
    return WorkboardTicket(**values)


@pytest.fixture
async def owner(async_session: AsyncSession) -> User:
    user = User(
        email="wb_run_owner@test.local",
        hashed_password="x",
        is_active=True,
        is_verified=True,
        is_superuser=False,
        full_name="Run Owner",
    )
    async_session.add(user)
    await async_session.commit()
    return user


class TestTheSettleQuotesItsRun:
    """A settle names the run it belongs to, and loses when it is stale."""

    async def test_a_run_settles_the_ticket_it_claimed(
        self, async_session: AsyncSession, owner: User
    ) -> None:
        repo = WorkboardRepository(async_session)
        ticket = _ticket(owner.id)
        async_session.add(ticket)
        await async_session.commit()

        claimed = await repo.claim_ticket(ticket, run_id="r-1", now=NOW)
        assert claimed is not None
        assert claimed.status == TicketStatus.IN_PROGRESS.value
        assert claimed.run_attempts == 1
        assert claimed.run_count == 1
        assert claimed.run_claimed_at is not None

        settled = await repo.settle_run(
            ticket_id=ticket.id,
            run_id="r-1",
            status=TicketStatus.VALIDATING.value,
            outcome=RunOutcome.SUCCESS.value,
            now=NOW + timedelta(minutes=2),
            usage=RunUsage(
                tokens_in=1200,
                tokens_out=340,
                tokens_cache=64,
                google_requests=2,
                cost_eur=Decimal("0.0042"),
            ),
        )
        await async_session.commit()

        assert settled is True
        stored = await async_session.get(WorkboardTicket, ticket.id, populate_existing=True)
        assert stored is not None
        assert stored.status == TicketStatus.VALIDATING.value
        assert stored.run_claimed_at is None
        assert stored.run_attempts == 0
        assert stored.run_count == 1
        assert stored.last_run_outcome == RunOutcome.SUCCESS.value
        assert stored.last_run_tokens_in == 1200
        assert stored.last_run_cost_eur == Decimal("0.004200")
        # The run's figures are ADDED to the ticket's own totals, by column
        # arithmetic in this very transaction — a read-modify-write in Python
        # would lose one of two runs settling at the same second.
        assert stored.total_tokens_in == 1200
        assert stored.total_tokens_out == 340
        assert stored.total_tokens_cache == 64
        assert stored.total_google_requests == 2
        assert stored.total_cost_eur == Decimal("0.004200")
        # The row decides how the NEXT run executes, and says so by default.
        assert stored.execution_mode == "react"

    async def test_a_person_who_moved_the_ticket_mid_run_wins(
        self, async_session: AsyncSession, owner: User
    ) -> None:
        """The whole reason the settle is conditional: the late write must not
        drag the ticket out of the column the person put it in."""
        repo = WorkboardRepository(async_session)
        ticket = _ticket(owner.id)
        async_session.add(ticket)
        await async_session.commit()
        await repo.claim_ticket(ticket, run_id="r-1", now=NOW)

        # The person cancels it while the run is in flight.
        moved = await async_session.get(WorkboardTicket, ticket.id, populate_existing=True)
        assert moved is not None
        moved.status = TicketStatus.DONE.value
        await async_session.commit()

        settled = await repo.settle_run(
            ticket_id=ticket.id,
            run_id="r-1",
            status=TicketStatus.VALIDATING.value,
            outcome=RunOutcome.SUCCESS.value,
            now=NOW + timedelta(minutes=2),
        )
        await async_session.commit()

        assert settled is False
        stored = await async_session.get(WorkboardTicket, ticket.id, populate_existing=True)
        assert stored is not None
        assert stored.status == TicketStatus.DONE.value

    async def test_a_settle_from_a_previous_run_lands_nowhere(
        self, async_session: AsyncSession, owner: User
    ) -> None:
        """A reaped run whose worker comes back to life must not settle the
        ticket a LATER run is holding."""
        repo = WorkboardRepository(async_session)
        ticket = _ticket(owner.id)
        async_session.add(ticket)
        await async_session.commit()

        await repo.claim_ticket(ticket, run_id="r-1", now=NOW)
        await repo.reap_stale_claims(older_than=NOW + timedelta(minutes=30))
        await async_session.commit()
        revived = await async_session.get(WorkboardTicket, ticket.id, populate_existing=True)
        assert revived is not None
        await repo.claim_ticket(revived, run_id="r-2", now=NOW + timedelta(hours=1))
        await async_session.commit()

        settled = await repo.settle_run(
            ticket_id=ticket.id,
            run_id="r-1",
            status=TicketStatus.DONE.value,
            outcome=RunOutcome.SUCCESS.value,
            now=NOW + timedelta(hours=2),
        )
        await async_session.commit()

        assert settled is False
        stored = await async_session.get(WorkboardTicket, ticket.id, populate_existing=True)
        assert stored is not None
        assert stored.status == TicketStatus.IN_PROGRESS.value
        assert stored.last_run_id == "r-2"


class TestTheClaimIsConditionalToo:
    async def test_a_second_claim_on_the_same_row_takes_nothing(
        self, async_session: AsyncSession, owner: User
    ) -> None:
        """The lock and the condition are two guards, not one.

        The race test cannot reach this one: ``SKIP LOCKED`` means the loser
        never holds the row to begin with. But the day somebody scans without
        locking — a refactor, a second reader, a replica — the UPDATE is what
        still refuses, and a guard nothing exercises is a guard nobody notices
        losing.
        """
        repo = WorkboardRepository(async_session)
        ticket = _ticket(owner.id)
        async_session.add(ticket)
        await async_session.commit()

        first = await repo.claim_ticket(ticket, run_id="r-1", now=NOW)
        second = await repo.claim_ticket(ticket, run_id="r-2", now=NOW)
        await async_session.commit()

        assert first is not None
        assert second is None
        stored = await async_session.get(WorkboardTicket, ticket.id, populate_existing=True)
        assert stored is not None
        assert stored.last_run_id == "r-1"
        assert stored.run_count == 1, "the refused claim must not have counted a run"


class TestARunThatNeverRan:
    async def test_a_quota_release_gives_the_run_back_and_backs_off(
        self, async_session: AsyncSession, owner: User
    ) -> None:
        repo = WorkboardRepository(async_session)
        ticket = _ticket(owner.id)
        async_session.add(ticket)
        await async_session.commit()
        await repo.claim_ticket(ticket, run_id="r-1", now=NOW)

        retry_at = NOW + timedelta(minutes=30)
        released = await repo.release_claim(
            ticket_id=ticket.id,
            run_id="r-1",
            outcome=RunOutcome.SKIPPED_QUOTA.value,
            now=NOW,
            retry_after=retry_at,
        )
        await async_session.commit()

        assert released is True
        stored = await async_session.get(WorkboardTicket, ticket.id, populate_existing=True)
        assert stored is not None
        assert stored.status == TicketStatus.TODO.value
        assert stored.run_claimed_at is None
        assert stored.run_count == 0, "a run that never ran costs nothing"
        assert stored.run_attempts == 0
        assert stored.run_not_before == retry_at
        assert stored.last_run_outcome == RunOutcome.SKIPPED_QUOTA.value

    async def test_the_back_off_takes_the_ticket_out_of_the_scan(
        self, async_session: AsyncSession, owner: User
    ) -> None:
        repo = WorkboardRepository(async_session)
        ticket = _ticket(owner.id, run_not_before=NOW + timedelta(minutes=30))
        async_session.add(ticket)
        await async_session.commit()

        stmt = repo.claimable_stmt(NOW, max_runs=10, max_attempts=3)
        assert (await async_session.execute(stmt)).scalars().first() is None

        later = repo.claimable_stmt(NOW + timedelta(hours=1), max_runs=10, max_attempts=3)
        assert (await async_session.execute(later)).scalars().first() is not None


#: Every dimension of the eligibility predicate, at its boundary rather than
#: at a sampled value. A wrong predicate here runs somebody's ticket at the
#: wrong moment, or never runs it at all and says nothing — so the cases are
#: ENUMERATED: the seven columns, both holders, and each bound just inside and
#: just outside.
ELIGIBILITY_CASES: list[tuple[str, dict[str, Any], bool]] = [
    (f"status {status.value}", {"status": status.value}, status is TicketStatus.TODO)
    for status in TicketStatus
] + [
    ("held by a person", {"assignee_kind": AssigneeKind.HUMAN.value}, False),
    ("held by LIA", {"assignee_kind": AssigneeKind.LIA.value}, True),
    ("already claimed", {"run_claimed_at": NOW - timedelta(minutes=1)}, False),
    ("never claimed", {"run_claimed_at": None}, True),
    ("starts tomorrow", {"start_at": NOW + timedelta(days=1)}, False),
    ("starts this very second", {"start_at": NOW}, True),
    ("started yesterday", {"start_at": NOW - timedelta(days=1)}, True),
    ("no start date at all", {"start_at": None}, True),
    ("backing off until later", {"run_not_before": NOW + timedelta(minutes=1)}, False),
    ("back-off expiring now", {"run_not_before": NOW}, True),
    ("no back-off", {"run_not_before": None}, True),
    ("one attempt short of the cap", {"run_attempts": 2}, True),
    ("at the attempts cap", {"run_attempts": 3}, False),
    ("past the attempts cap", {"run_attempts": 4}, False),
    ("one run short of the cap", {"run_count": 9}, True),
    ("at the runs cap", {"run_count": 10}, False),
    ("past the runs cap", {"run_count": 11}, False),
]


class TestTheEligibilityPredicate:
    @pytest.mark.parametrize(
        ("label", "overrides", "eligible"),
        ELIGIBILITY_CASES,
        ids=[case[0] for case in ELIGIBILITY_CASES],
    )
    async def test_each_dimension_at_its_boundary(
        self,
        async_session: AsyncSession,
        owner: User,
        label: str,
        overrides: dict[str, Any],
        eligible: bool,
    ) -> None:
        ticket = _ticket(owner.id, title=label, **overrides)
        async_session.add(ticket)
        await async_session.commit()

        stmt = WorkboardRepository(async_session).claimable_stmt(NOW, max_runs=10, max_attempts=3)
        offered = (await async_session.execute(stmt)).scalars().first()

        assert (offered is not None) is eligible, label


class TestTheScanOnARealServer:
    async def test_it_offers_only_what_lia_holds_and_is_ready(
        self, async_session: AsyncSession, owner: User
    ) -> None:
        repo = WorkboardRepository(async_session)
        async_session.add_all(
            [
                _ticket(owner.id, title="An idea", status=TicketStatus.IDEA.value),
                _ticket(owner.id, title="Mine", assignee_kind=AssigneeKind.HUMAN.value),
                _ticket(owner.id, title="Later", start_at=NOW + timedelta(days=1)),
                _ticket(owner.id, title="Spent", run_count=10),
                _ticket(owner.id, title="Stuck", run_attempts=3),
                _ticket(owner.id, title="Held", run_claimed_at=NOW),
                _ticket(owner.id, title="Ready", start_at=NOW - timedelta(hours=1)),
            ]
        )
        await async_session.commit()

        stmt = repo.claimable_stmt(NOW, max_runs=10, max_attempts=3)
        offered = (await async_session.execute(stmt)).scalars().first()

        assert offered is not None
        assert offered.title == "Ready"

    async def test_a_ticket_ready_longer_goes_first(
        self, async_session: AsyncSession, owner: User
    ) -> None:
        repo = WorkboardRepository(async_session)
        async_session.add_all(
            [
                _ticket(owner.id, title="Recent", start_at=NOW - timedelta(minutes=5)),
                _ticket(owner.id, title="Oldest", start_at=NOW - timedelta(days=3)),
            ]
        )
        await async_session.commit()

        stmt = repo.claimable_stmt(NOW, max_runs=10, max_attempts=3)
        offered = (await async_session.execute(stmt)).scalars().first()

        assert offered is not None
        assert offered.title == "Oldest"


class TestReaping:
    async def test_a_stranded_claim_comes_back_with_its_attempt_counted(
        self, async_session: AsyncSession, owner: User
    ) -> None:
        """The attempt is what stops an unrunnable ticket looping for ever, so
        the reaper must NOT clear it — that is the settle's job."""
        repo = WorkboardRepository(async_session)
        ticket = _ticket(owner.id)
        async_session.add(ticket)
        await async_session.commit()
        await repo.claim_ticket(ticket, run_id="r-1", now=NOW)
        await async_session.commit()

        reaped = await repo.reap_stale_claims(older_than=NOW + timedelta(minutes=30))
        await async_session.commit()

        assert reaped == 1
        stored = await async_session.get(WorkboardTicket, ticket.id, populate_existing=True)
        assert stored is not None
        assert stored.status == TicketStatus.TODO.value
        assert stored.run_claimed_at is None
        assert stored.run_attempts == 1, "the attempt happened, and it counts"
        assert stored.run_count == 1
        assert stored.last_run_outcome == RunOutcome.FAILED.value
        assert (
            stored.last_run_error == RunError.RUN_REAPED.value
        ), "a card must say the run was reaped, not repeat an older message"

    async def test_a_fresh_claim_is_left_alone(
        self, async_session: AsyncSession, owner: User
    ) -> None:
        repo = WorkboardRepository(async_session)
        ticket = _ticket(owner.id)
        async_session.add(ticket)
        await async_session.commit()
        await repo.claim_ticket(ticket, run_id="r-1", now=NOW)
        await async_session.commit()

        assert await repo.reap_stale_claims(older_than=NOW - timedelta(minutes=1)) == 0


class TestThePrice:
    async def test_a_second_run_adds_to_the_ticket_total(
        self, async_session: AsyncSession, owner: User
    ) -> None:
        """The last run is a snapshot; the totals are a LIFE."""
        repo = WorkboardRepository(async_session)
        ticket = _ticket(owner.id)
        async_session.add(ticket)
        await async_session.commit()

        for index, (run_id, spent) in enumerate((("r-1", 100), ("r-2", 30))):
            claimed = await repo.claim_ticket(ticket, run_id=run_id, now=NOW)
            assert claimed is not None
            await repo.settle_run(
                ticket_id=ticket.id,
                run_id=run_id,
                status=TicketStatus.TODO.value,
                outcome=RunOutcome.SUCCESS.value,
                now=NOW + timedelta(minutes=index + 1),
                usage=RunUsage(
                    tokens_in=spent,
                    tokens_out=spent,
                    tokens_cache=spent,
                    google_requests=1,
                    cost_eur=Decimal("0.001"),
                ),
            )
            await async_session.commit()

        stored = await async_session.get(WorkboardTicket, ticket.id, populate_existing=True)
        assert stored is not None
        assert stored.last_run_tokens_in == 30
        assert stored.total_tokens_in == 130
        assert stored.total_tokens_out == 130
        assert stored.total_tokens_cache == 130
        assert stored.total_google_requests == 2
        assert stored.total_cost_eur == Decimal("0.002000")

    async def test_the_summary_of_the_turn_is_the_authority(
        self, async_session: AsyncSession, owner: User
    ) -> None:
        """One row per turn, the same the chat's own totals are built from."""
        async_session.add(
            MessageTokenSummary(
                user_id=owner.id,
                session_id="s-9",
                run_id="r-9",
                total_prompt_tokens=1200,
                total_completion_tokens=340,
                total_cached_tokens=64,
                google_api_requests=2,
                total_cost_eur=Decimal("0.0042"),
            )
        )
        await async_session.commit()

        usage = await WorkboardRepository(async_session).run_usage("r-9")

        assert usage == RunUsage(
            tokens_in=1200,
            tokens_out=340,
            tokens_cache=64,
            google_requests=2,
            cost_eur=Decimal("0.0042"),
        )

    async def test_the_cost_sums_every_call_of_the_run(
        self, async_session: AsyncSession, owner: User
    ) -> None:
        async_session.add_all(
            [
                TokenUsageLog(
                    user_id=owner.id,
                    run_id="r-1",
                    node_name="router",
                    model_name="gpt-5.6-luna",
                    prompt_tokens=800,
                    completion_tokens=120,
                    cost_eur=Decimal("0.0030"),
                ),
                TokenUsageLog(
                    user_id=owner.id,
                    run_id="r-1",
                    node_name="response",
                    model_name="gpt-5.6-luna",
                    prompt_tokens=400,
                    completion_tokens=220,
                    cost_eur=Decimal("0.0012"),
                ),
                TokenUsageLog(
                    user_id=owner.id,
                    run_id="r-2",
                    node_name="router",
                    model_name="gpt-5.6-luna",
                    prompt_tokens=9999,
                    completion_tokens=9999,
                    cost_eur=Decimal("9.9999"),
                ),
            ]
        )
        await async_session.commit()

        usage = await WorkboardRepository(async_session).run_usage("r-1")

        # No summary row for this run: the per-node log is the FALLBACK, and
        # it knows nothing of Google calls.
        assert usage.tokens_in == 1200
        assert usage.tokens_out == 340
        assert usage.cost_eur == Decimal("0.0042")
        assert usage.google_requests == 0

    async def test_a_run_that_called_no_model_prices_at_zero(
        self, async_session: AsyncSession, owner: User
    ) -> None:
        """SUM over an empty set is NULL, and a NULL price would render as
        « unknown » where the true answer is « nothing »."""
        assert await WorkboardRepository(async_session).run_usage("never-ran") == RunUsage(
            tokens_in=0,
            tokens_out=0,
            tokens_cache=0,
            google_requests=0,
            cost_eur=Decimal(0),
        )


class TestRetention:
    @staticmethod
    def _message(conversation_id: UUID, ticket_id: UUID | None, *, hidden: bool) -> Any:
        metadata: dict[str, Any] = {}
        if ticket_id is not None:
            metadata = {
                "hidden": hidden,
                RUN_ORIGIN_KIND: {"ticket_id": str(ticket_id), "run_id": "r-1"},
            }
        return ConversationMessage(
            conversation_id=conversation_id,
            role="assistant",
            content="The venue is booked.",
            hidden=hidden,
            message_metadata=metadata or None,
        )

    async def test_only_the_transcripts_of_long_closed_tickets_go(
        self, async_session: AsyncSession, owner: User
    ) -> None:
        conversation = Conversation(
            user_id=owner.id, title="Thread", message_count=0, total_tokens=0
        )
        async_session.add(conversation)
        closed_long_ago = _ticket(
            owner.id,
            title="Closed long ago",
            status=TicketStatus.DONE.value,
            status_changed_at=NOW - timedelta(days=180),
        )
        closed_recently = _ticket(
            owner.id,
            title="Closed yesterday",
            status=TicketStatus.DONE.value,
            status_changed_at=NOW - timedelta(days=1),
        )
        still_open = _ticket(owner.id, title="Still open", status=TicketStatus.WAITING.value)
        async_session.add_all([closed_long_ago, closed_recently, still_open])
        await async_session.commit()

        async_session.add_all(
            [
                self._message(conversation.id, closed_long_ago.id, hidden=True),
                self._message(conversation.id, closed_recently.id, hidden=True),
                self._message(conversation.id, still_open.id, hidden=True),
                # A visible row of the same conversation: the person's own turn.
                self._message(conversation.id, None, hidden=False),
            ]
        )
        await async_session.commit()

        removed = await WorkboardRepository(async_session).purge_hidden_rows(
            closed_before=NOW - timedelta(days=90)
        )
        await async_session.commit()

        assert removed == 1
        left = (
            await async_session.execute(
                select(func.count())
                .select_from(ConversationMessage)
                .where(ConversationMessage.conversation_id == conversation.id)
            )
        ).scalar()
        assert left == 3

    async def test_the_rows_of_a_deleted_ticket_go_once_old_enough(
        self, async_session: AsyncSession, owner: User
    ) -> None:
        """The defect the first purge had: it joined on EXISTING tickets, so the
        rows of a deleted one were never reached and grew for ever."""
        conversation = Conversation(
            user_id=owner.id, title="Thread", message_count=0, total_tokens=0
        )
        async_session.add(conversation)
        await async_session.commit()
        orphan_ticket_id = uuid4()  # a ticket that no longer exists
        old = self._message(conversation.id, orphan_ticket_id, hidden=True)
        old.created_at = NOW - timedelta(days=180)
        recent = self._message(conversation.id, orphan_ticket_id, hidden=True)
        recent.created_at = NOW - timedelta(days=1)
        async_session.add_all([old, recent])
        await async_session.commit()

        removed = await WorkboardRepository(async_session).purge_hidden_rows(
            closed_before=NOW - timedelta(days=90)
        )
        await async_session.commit()

        assert removed == 1, "the old orphan goes, the recent one waits its window"

    async def test_a_visible_row_of_a_closed_ticket_is_never_touched(
        self, async_session: AsyncSession, owner: User
    ) -> None:
        """``hidden`` is the whole licence to delete: a row a person can read
        in their chat belongs to them, whatever ticket it mentions."""
        conversation = Conversation(
            user_id=owner.id, title="Thread", message_count=0, total_tokens=0
        )
        async_session.add(conversation)
        closed = _ticket(
            owner.id,
            title="Closed long ago",
            status=TicketStatus.DONE.value,
            status_changed_at=NOW - timedelta(days=180),
        )
        async_session.add(closed)
        await async_session.commit()
        async_session.add(self._message(conversation.id, closed.id, hidden=False))
        await async_session.commit()

        removed = await WorkboardRepository(async_session).purge_hidden_rows(
            closed_before=NOW - timedelta(days=90)
        )
        assert removed == 0


# --------------------------------------------------------------------------
# Two workers, one ticket. This needs REAL connections: the savepoint-isolated
# ``async_session`` keeps everything inside one uncommitted transaction, so a
# second connection would see no ticket at all and the race would « pass » by
# finding nothing to fight over.
# --------------------------------------------------------------------------


@pytest_asyncio.fixture
async def racing_sessions(async_engine: Any, test_database_url: str) -> Any:
    """A pooled sessionmaker whose writes really commit, and its clean-up.

    Depends on ``async_engine`` so the schema exists. Rows written here outlive
    the test by construction, so the fixture deletes the account it created —
    every table under test hangs off it by CASCADE.
    """
    engine = create_async_engine(test_database_url, echo=False)
    maker = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    marker = f"wb_race_{uuid4().hex}@test.local"
    yield maker, marker
    async with maker() as session:
        await session.execute(delete(User).where(User.email == marker))
        await session.commit()
    await engine.dispose()


async def _seed_one_claimable_ticket(maker: Any, email: str) -> UUID:
    """One account, one ticket LIA may run, really committed."""
    async with maker() as session:
        user = User(
            email=email,
            hashed_password="x",
            is_active=True,
            is_verified=True,
            is_superuser=False,
            full_name="Race Owner",
        )
        session.add(user)
        await session.commit()
        ticket = _ticket(user.id, start_at=NOW - timedelta(hours=1))
        session.add(ticket)
        await session.commit()
        return ticket.id


async def _claim_once(maker: Any, run_id: str, hold_seconds: float) -> WorkboardTicket | None:
    """Scan, hold the lock for a moment, then claim — one worker's whole life."""
    async with maker() as session, session.begin():
        repo = WorkboardRepository(session)
        offered = (
            (await session.execute(repo.claimable_stmt(NOW, max_runs=10, max_attempts=3)))
            .scalars()
            .first()
        )
        if offered is None:
            return None
        # The window a second worker would use, if the row were not locked.
        await asyncio.sleep(hold_seconds)
        return await repo.claim_ticket(offered, run_id=run_id, now=NOW)


async def _timed_claim(
    maker: Any, run_id: str, hold_seconds: float
) -> tuple[WorkboardTicket | None, float]:
    """The same worker, timing ITSELF.

    The gather's own duration proves nothing — it is the winner's hold either
    way. What separates ``SKIP LOCKED`` from a plain ``FOR UPDATE`` is how long
    the LOSER spent before giving up.
    """
    started = asyncio.get_running_loop().time()
    claimed = await _claim_once(maker, run_id, hold_seconds)
    return claimed, asyncio.get_running_loop().time() - started


class TestTwoWorkersOneTicket:
    async def test_exactly_one_worker_takes_it(self, racing_sessions: Any) -> None:
        maker, email = racing_sessions
        ticket_id = await _seed_one_claimable_ticket(maker, email)

        first, second = await asyncio.gather(
            _claim_once(maker, "r-first", hold_seconds=0.4),
            _claim_once(maker, "r-second", hold_seconds=0.0),
        )

        claimed = [result for result in (first, second) if result is not None]
        assert len(claimed) == 1, "SKIP LOCKED must hand the row to exactly one worker"

        async with maker() as session:
            stored = await session.get(WorkboardTicket, ticket_id)
            assert stored is not None
            assert stored.status == TicketStatus.IN_PROGRESS.value
            assert stored.run_count == 1, "the loser must not have counted a run"
            assert stored.run_attempts == 1
            assert stored.last_run_id == claimed[0].last_run_id

    async def test_the_loser_steps_over_rather_than_waiting(self, racing_sessions: Any) -> None:
        """SKIP LOCKED, not FOR UPDATE alone.

        A worker that QUEUED on the lock would sit there for the whole run and
        only then discover the ticket is gone — one sweep tick spent doing
        nothing, and a worker pool that serialises on the busiest ticket
        instead of moving to the next one. The oracle is the LOSER's own
        duration: it must not have waited for the winner.
        """
        maker, email = racing_sessions
        await _seed_one_claimable_ticket(maker, email)

        hold = 0.8
        (_winner, _), (loser, loser_seconds) = await asyncio.gather(
            _timed_claim(maker, "r-first", hold_seconds=hold),
            _timed_claim(maker, "r-second", hold_seconds=0.0),
        )

        assert loser is None
        assert loser_seconds < hold / 2, (
            f"the loser spent {loser_seconds:.2f}s — it queued behind the winner's lock "
            f"instead of stepping over it"
        )
