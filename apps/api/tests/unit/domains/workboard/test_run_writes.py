"""Claiming a ticket, settling its run, and pricing it (ADR-276).

Three writes the sweep makes, and the rules each one enforces:

- **the claim is conditional and atomic.** ``FOR UPDATE SKIP LOCKED`` picks a
  ticket no other worker holds, and the same statement moves it to
  ``in_progress`` — a claim followed by work outside the claiming transaction
  is the forbidden shape (the repository's own doctrine).
- **the settle quotes the run it belongs to.** A person who moved the ticket
  mid-run WINS: the late settle matches nothing and says so, rather than
  dragging the ticket back to a column they left.
- **the cost is one aggregate.** ``token_usage_logs`` is BILLING_RETAINED and
  outlives the account, so the price is snapshotted onto the ticket rather
  than joined at render time.

Behaviour against a real server — two workers racing for one ticket, a settle
losing to a person — is proved in ``tests/integration/domains/workboard``.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from unittest.mock import AsyncMock, MagicMock

import pytest
from sqlalchemy.dialects import postgresql

from src.domains.workboard.constants import RunOutcome, TicketStatus
from src.domains.workboard.repository import WorkboardRepository

pytestmark = pytest.mark.unit

NOW = datetime(2026, 9, 9, 12, 0, tzinfo=UTC)


def _repo() -> WorkboardRepository:
    return WorkboardRepository(AsyncMock())


def _sql(statement: object) -> str:
    return str(
        statement.compile(  # type: ignore[attr-defined]
            dialect=postgresql.dialect(), compile_kwargs={"literal_binds": True}
        )
    )


class TestWhichTicketTheSweepTakes:
    def test_it_takes_only_what_lia_holds_and_is_ready(self) -> None:
        sql = _sql(_repo().claimable_stmt(NOW, max_runs=10, max_attempts=3))
        assert "assignee_kind = 'lia'" in sql
        assert "status = 'todo'" in sql
        assert "run_claimed_at IS NULL" in sql

    def test_an_idea_is_never_run(self) -> None:
        """Noted is not engaged: the column exists so a thought can wait."""
        sql = _sql(_repo().claimable_stmt(NOW, max_runs=10, max_attempts=3))
        assert TicketStatus.IDEA.value not in sql

    def test_a_start_date_in_the_future_waits(self) -> None:
        sql = _sql(_repo().claimable_stmt(NOW, max_runs=10, max_attempts=3))
        assert "start_at IS NULL" in sql
        assert "start_at <=" in sql

    def test_a_quota_back_off_is_respected(self) -> None:
        sql = _sql(_repo().claimable_stmt(NOW, max_runs=10, max_attempts=3))
        assert "run_not_before IS NULL" in sql
        assert "run_not_before <=" in sql

    def test_both_caps_bound_the_scan(self) -> None:
        """The runs cap bounds the hidden transcripts; the attempts cap stops a
        ticket that keeps failing from being retried for ever."""
        sql = _sql(_repo().claimable_stmt(NOW, max_runs=10, max_attempts=3))
        assert "run_count < 10" in sql
        assert "run_attempts < 3" in sql

    def test_it_locks_the_row_and_steps_over_the_ones_others_hold(self) -> None:
        sql = _sql(_repo().claimable_stmt(NOW, max_runs=10, max_attempts=3))
        assert "FOR UPDATE" in sql
        assert "SKIP LOCKED" in sql

    def test_it_takes_one_ticket_at_a_time(self) -> None:
        """A worker that claimed five and crashed strands five."""
        assert "LIMIT 1" in _sql(_repo().claimable_stmt(NOW, max_runs=10, max_attempts=3))

    def test_the_oldest_start_goes_first(self) -> None:
        sql = _sql(_repo().claimable_stmt(NOW, max_runs=10, max_attempts=3))
        order_by = sql.split("ORDER BY", 1)[1]
        assert "start_at" in order_by
        assert order_by.strip().split()[-1].endswith("id") or "id" in order_by


class TestTakingIt:
    async def test_the_claim_moves_it_and_counts_the_run(self) -> None:
        repo = _repo()
        ticket = MagicMock(id=uuid.uuid4(), run_count=2, run_attempts=0)
        repo.db.execute = AsyncMock(return_value=MagicMock(scalar_one_or_none=lambda: ticket))

        claimed = await repo.claim_ticket(ticket, run_id="r-1", now=NOW)

        assert claimed is ticket
        sql = _sql(repo.db.execute.await_args.args[0])
        assert "UPDATE workboard_tickets" in sql
        assert "status='in_progress'" in sql.replace(" ", "")
        assert "last_run_id='r-1'" in sql.replace(" ", "")
        assert "RETURNING" in sql

    async def test_the_claim_only_takes_a_ticket_still_free(self) -> None:
        """Between the scan and the write another worker may have taken it."""
        repo = _repo()
        ticket = MagicMock(id=uuid.uuid4())
        repo.db.execute = AsyncMock(return_value=MagicMock(scalar_one_or_none=lambda: None))

        assert await repo.claim_ticket(ticket, run_id="r-1", now=NOW) is None

        where = _sql(repo.db.execute.await_args.args[0]).split("WHERE", 1)[1]
        assert "run_claimed_at IS NULL" in where
        assert "status = 'todo'" in where


class TestSettlingIt:
    async def test_the_settle_names_the_run_it_belongs_to(self) -> None:
        """A person who moved the ticket mid-run wins; the late settle must
        match nothing rather than drag it back."""
        repo = _repo()
        repo.db.execute = AsyncMock(return_value=MagicMock(rowcount=1))

        settled = await repo.settle_run(
            ticket_id=uuid.uuid4(),
            run_id="r-1",
            status=TicketStatus.VALIDATING.value,
            outcome=RunOutcome.SUCCESS.value,
            now=NOW,
        )

        assert settled is True
        where = _sql(repo.db.execute.await_args.args[0]).split("WHERE", 1)[1]
        assert "last_run_id = 'r-1'" in where
        assert "status = 'in_progress'" in where

    async def test_a_lost_settle_says_so(self) -> None:
        repo = _repo()
        repo.db.execute = AsyncMock(return_value=MagicMock(rowcount=0))
        assert (
            await repo.settle_run(
                ticket_id=uuid.uuid4(),
                run_id="r-1",
                status=TicketStatus.VALIDATING.value,
                outcome=RunOutcome.SUCCESS.value,
                now=NOW,
            )
            is False
        )

    async def test_it_releases_the_claim_and_stamps_the_outcome(self) -> None:
        repo = _repo()
        repo.db.execute = AsyncMock(return_value=MagicMock(rowcount=1))
        await repo.settle_run(
            ticket_id=uuid.uuid4(),
            run_id="r-1",
            status=TicketStatus.WAITING.value,
            outcome=RunOutcome.WAITING.value,
            now=NOW,
            error="workboard_needs_you: send_email_tool",
        )
        assignments = _sql(repo.db.execute.await_args.args[0]).split("WHERE", 1)[0]
        assert "run_claimed_at=NULL" in assignments.replace(" ", "")
        assert "last_run_outcome='waiting'" in assignments.replace(" ", "")
        assert "last_run_error=" in assignments.replace(" ", "")

    async def test_a_settle_that_hands_the_ticket_back_clears_the_attempts(self) -> None:
        """The attempts counter bounds ONE run, not the ticket's lifetime."""
        repo = _repo()
        repo.db.execute = AsyncMock(return_value=MagicMock(rowcount=1))
        await repo.settle_run(
            ticket_id=uuid.uuid4(),
            run_id="r-1",
            status=TicketStatus.VALIDATING.value,
            outcome=RunOutcome.SUCCESS.value,
            now=NOW,
        )
        assignments = _sql(repo.db.execute.await_args.args[0]).split("WHERE", 1)[0]
        assert "run_attempts=0" in assignments.replace(" ", "")


class TestReleasingWithoutSettling:
    async def test_a_skipped_run_gives_the_ticket_straight_back(self) -> None:
        """Quota-blocked or busy: nothing ran, so the ticket returns to `todo`
        and its run must not be counted against the lifetime cap."""
        repo = _repo()
        repo.db.execute = AsyncMock(return_value=MagicMock(rowcount=1))

        await repo.release_claim(
            ticket_id=uuid.uuid4(),
            run_id="r-1",
            outcome=RunOutcome.SKIPPED_QUOTA.value,
            now=NOW,
            retry_after=NOW + timedelta(minutes=30),
        )

        assignments = _sql(repo.db.execute.await_args.args[0]).split("WHERE", 1)[0].replace(" ", "")
        assert "status='todo'" in assignments
        assert "run_claimed_at=NULL" in assignments
        assert "run_count=" in assignments, "the run it did not make is given back"
        assert "run_not_before=" in assignments


class TestPricingIt:
    async def test_it_reads_the_consolidated_record_the_chat_reads(self) -> None:
        """One row per run in ``message_token_summary``, carrying the five
        figures the chat shows: a ticket and a conversation can then never
        state the same run differently."""
        repo = _repo()
        repo.db.execute = AsyncMock(
            return_value=MagicMock(first=lambda: (1200, 340, 512, 3, 0.0042))
        )

        usage = await repo.run_usage("r-1")

        assert (usage.tokens_in, usage.tokens_out, usage.tokens_cache) == (1200, 340, 512)
        assert (usage.google_requests, usage.cost_eur) == (3, 0.0042)
        sql = _sql(repo.db.execute.await_args.args[0])
        assert "message_token_summary" in sql
        assert "run_id = 'r-1'" in sql

    async def test_without_that_record_it_sums_the_per_node_rows(self) -> None:
        """The fallback is what the summary is itself built from, never a
        second authority: a run that broke before the summary was written
        still has its per-node rows."""
        repo = _repo()
        repo.db.execute = AsyncMock(
            return_value=MagicMock(first=lambda: None, one=lambda: (900, 120, 64, 0.0031))
        )

        usage = await repo.run_usage("r-1")

        assert (usage.tokens_in, usage.tokens_out, usage.tokens_cache) == (900, 120, 64)
        assert (usage.google_requests, usage.cost_eur) == (0, 0.0031)
        sql = _sql(repo.db.execute.await_args.args[0])
        assert "sum(" in sql.lower()

    async def test_a_run_that_spent_nothing_prices_at_zero(self) -> None:
        """A ticket answered from context alone still gets a settled price."""
        repo = _repo()
        # No consolidated summary for this run, and no per-node rows either:
        # the fallback answers zeros rather than nothing at all.
        repo.db.execute = AsyncMock(
            return_value=MagicMock(first=lambda: None, one=lambda: (None, None, None, None))
        )
        empty = await repo.run_usage("r-1")
        assert (empty.tokens_in, empty.tokens_out, empty.cost_eur) == (0, 0, 0.0)


class TestReapingAndRetention:
    async def test_a_stale_claim_is_released_not_settled(self) -> None:
        """A worker killed mid-run leaves a ticket claimed for ever otherwise."""
        repo = _repo()
        repo.db.execute = AsyncMock(return_value=MagicMock(rowcount=2))

        assert await repo.reap_stale_claims(older_than=NOW - timedelta(minutes=10)) == 2

        sql = _sql(repo.db.execute.await_args.args[0])
        assert "status='todo'" in sql.replace(" ", "")
        assert "run_claimed_at=NULL" in sql.replace(" ", "")
        where = sql.split("WHERE", 1)[1]
        assert "run_claimed_at <" in where

    async def test_the_retention_only_touches_closed_tickets_transcripts(self) -> None:
        repo = _repo()
        repo.db.execute = AsyncMock(return_value=MagicMock(rowcount=7))

        assert await repo.purge_hidden_rows(closed_before=NOW - timedelta(days=90)) == 7

        sql = _sql(repo.db.execute.await_args.args[0])
        assert "DELETE FROM conversation_messages" in sql
        assert "hidden" in sql
        assert "status_changed_at <" in sql
        assert "'done'" in sql


class TestTheDraftOnTheRow:
    """Lot 7: the settle stores, clears, or leaves alone the draft to confirm."""

    async def _settle(self, **extra: object) -> str:
        repo = _repo()
        repo.db.execute = AsyncMock(return_value=MagicMock(rowcount=1))
        await repo.settle_run(
            ticket_id=uuid.uuid4(),
            run_id="r-1",
            status=TicketStatus.CONFIRMING.value,
            outcome=RunOutcome.CONFIRMING.value,
            now=NOW,
            **extra,
        )
        statement = repo.db.execute.await_args.args[0]
        return str(statement.compile(dialect=postgresql.dialect())).split("WHERE", 1)[0]

    async def test_a_settle_stores_the_draft_the_person_must_confirm(self) -> None:
        assignments = await self._settle(pending_action={"draft_id": "d-1", "approved": False})
        assert "pending_action=" in assignments.replace(" ", "")

    async def test_a_settle_clears_it_with_an_explicit_none(self) -> None:
        assignments = await self._settle(pending_action=None)
        assert "pending_action=" in assignments.replace(" ", "")

    async def test_a_settle_that_says_nothing_leaves_it_alone(self) -> None:
        """A FAILED run must not spend an approval a retry can still replay."""
        assignments = await self._settle()
        assert "pending_action" not in assignments


class TestTheOwnersNotes:
    """Lot 7: the one comment query the brief asks pins its author by shape."""

    @staticmethod
    def _repo_returning(rows: list[object]) -> WorkboardRepository:
        repo = _repo()
        repo.db.execute = AsyncMock(
            return_value=MagicMock(scalars=lambda: MagicMock(all=lambda: list(rows)))
        )
        return repo

    async def test_the_query_pins_the_author_and_the_kind(self) -> None:
        repo = self._repo_returning([])
        owner = uuid.uuid4()
        await repo.owner_notes_since(uuid.uuid4(), owner, since=NOW, limit=3)

        sql = _sql(repo.db.execute.await_args.args[0])
        assert f"author_user_id = '{owner}'" in sql
        assert "author_kind = 'user'" in sql
        assert "created_at > " in sql
        assert "LIMIT 3" in sql

    async def test_without_a_last_run_every_note_counts(self) -> None:
        repo = self._repo_returning([])
        await repo.owner_notes_since(uuid.uuid4(), uuid.uuid4(), since=None, limit=3)
        assert "created_at >" not in _sql(repo.db.execute.await_args.args[0])

    async def test_the_latest_are_kept_and_come_back_oldest_first(self) -> None:
        newest, middle, oldest = object(), object(), object()
        repo = self._repo_returning([newest, middle, oldest])
        notes = await repo.owner_notes_since(uuid.uuid4(), uuid.uuid4(), since=None, limit=3)
        assert notes == [oldest, middle, newest]
        sql = _sql(repo.db.execute.await_args.args[0])
        assert "ORDER BY workboard_comments.created_at DESC" in sql


class TestTheTicketsRunningTotal:
    """Lot 11: « what did this cost me » is a question about the TICKET.

    A ticket is run up to ten times, so the figures are ADDED by the settle
    statement itself — a SELECT-then-add would lose a concurrent settle, which
    is the repository's own rule for every counter.
    """

    async def _settled_assignments(self, **extra: object) -> str:
        from src.domains.workboard.repository import RunUsage

        repo = _repo()
        repo.db.execute = AsyncMock(return_value=MagicMock(rowcount=1))
        await repo.settle_run(
            ticket_id=uuid.uuid4(),
            run_id="r-1",
            status=TicketStatus.VALIDATING.value,
            outcome=RunOutcome.SUCCESS.value,
            now=NOW,
            usage=RunUsage(
                tokens_in=1200,
                tokens_out=340,
                tokens_cache=512,
                google_requests=3,
                cost_eur=Decimal("0.5"),
            ),
            **extra,
        )
        return _sql(repo.db.execute.await_args.args[0]).split("WHERE", 1)[0]

    async def test_every_figure_is_added_to_the_ticket_by_the_database(self) -> None:
        assignments = (await self._settled_assignments()).replace(" ", "")

        for column in (
            "total_tokens_in",
            "total_tokens_out",
            "total_tokens_cache",
            "total_google_requests",
            "total_cost_eur",
        ):
            assert f"{column}=(workboard_tickets.{column}+" in assignments, column

    async def test_the_last_run_keeps_its_own_snapshot(self) -> None:
        """The panel names the LAST run beside the running total: two readings
        of one settle, never two sources."""
        assignments = (await self._settled_assignments()).replace(" ", "")

        assert "last_run_tokens_in=" in assignments
        assert "last_run_cost_eur=" in assignments

    async def test_a_settle_with_nothing_measured_adds_nothing(self) -> None:
        """A refusal settles the row without a run behind it: adding zeros
        would be honest, adding nothing is cheaper and says the same."""
        repo = _repo()
        repo.db.execute = AsyncMock(return_value=MagicMock(rowcount=1))
        await repo.settle_run(
            ticket_id=uuid.uuid4(),
            run_id="r-1",
            status=TicketStatus.IN_PROGRESS.value,
            outcome=RunOutcome.FAILED.value,
            now=NOW,
        )
        assignments = _sql(repo.db.execute.await_args.args[0]).split("WHERE", 1)[0]

        assert "total_tokens_in" not in assignments
