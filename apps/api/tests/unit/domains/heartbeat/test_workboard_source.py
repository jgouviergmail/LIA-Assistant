"""The workboard as a heartbeat source (ADR-276 D14, lot 6).

Covers what the fetcher hands the decision, the reason it puts on each ticket,
and the cooldown bump that runs only after a delivered notification actually
used the source.

The narrowing itself lives in SQL and is proved against a real PostgreSQL
server (``tests/integration/domains/workboard/test_nudge_query_db.py``): a
board may hold thousands of tickets and the decision wants a handful, so
filtering here would make the cap a formality. What these tests own is
everything the query cannot decide — the flag, the wording, the precedence
between two true reasons, and who may be bumped.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta
from types import SimpleNamespace
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from src.domains.heartbeat.context_sources import fetch_workboard_context
from src.domains.heartbeat.proactive_task import _bump_used_workboard

pytestmark = pytest.mark.unit

NOW = datetime.now(UTC)
REPO = "src.domains.workboard.repository.WorkboardRepository"


def _settings(**overrides: Any) -> SimpleNamespace:
    defaults: dict[str, Any] = {
        "workboard_enabled": True,
        "workboard_nudge_due_hours": 24,
        "workboard_nudge_waiting_hours": 48,
        "workboard_nudge_cooldown_days": 2,
        "workboard_nudge_max_items": 8,
    }
    defaults.update(overrides)
    return SimpleNamespace(**defaults)


def _ticket(
    *,
    title: str = "Réserver la salle",
    status: str = "todo",
    priority: str = "high",
    due_at: datetime | None = None,
    status_changed_at: datetime | None = None,
    assignee_kind: str = "human",
) -> SimpleNamespace:
    return SimpleNamespace(
        id=uuid.uuid4(),
        title=title,
        status=status,
        priority=priority,
        due_at=due_at,
        status_changed_at=status_changed_at or NOW,
        assignee_kind=assignee_kind,
    )


def _user(timezone: str = "Europe/Paris") -> SimpleNamespace:
    return SimpleNamespace(timezone=timezone)


async def _fetch(
    tickets: list[Any],
    *,
    said: dict[uuid.UUID, str] | None = None,
    **setting_overrides: Any,
) -> list[dict[str, Any]] | None:
    with (
        patch(f"{REPO}.list_nudge_worthy", AsyncMock(return_value=tickets)),
        patch(f"{REPO}.latest_lia_comments", AsyncMock(return_value=said or {})),
    ):
        return await fetch_workboard_context(
            MagicMock(), uuid.uuid4(), _user(), _settings(**setting_overrides)
        )


class TestWhyATicketSurfaced:
    async def test_a_past_due_date_reads_overdue(self) -> None:
        entries = await _fetch([_ticket(due_at=NOW - timedelta(hours=3))])

        assert entries is not None
        assert entries[0]["reason"] == "overdue"

    async def test_a_due_date_inside_the_window_reads_due_soon(self) -> None:
        entries = await _fetch([_ticket(due_at=NOW + timedelta(hours=3))])

        assert entries is not None
        assert entries[0]["reason"] == "due_soon"

    async def test_a_stopped_ticket_reads_waiting(self) -> None:
        entries = await _fetch(
            [_ticket(status="waiting", status_changed_at=NOW - timedelta(days=5))]
        )

        assert entries is not None
        assert entries[0]["reason"] == "waiting"

    async def test_a_confirmation_awaited_reads_confirming(self) -> None:
        """Lot 7: LIA prepared an action and the person has not answered."""
        entries = await _fetch(
            [_ticket(status="confirming", status_changed_at=NOW - timedelta(days=5))]
        )

        assert entries is not None
        assert entries[0]["reason"] == "confirming"

    async def test_overdue_WINS_over_waiting(self) -> None:
        """Both are true of the same ticket, and the person needs the sharper
        of the two facts — not both, and not the milder one."""
        entries = await _fetch(
            [
                _ticket(
                    status="waiting",
                    status_changed_at=NOW - timedelta(days=5),
                    due_at=NOW - timedelta(hours=1),
                )
            ]
        )

        assert entries is not None
        assert entries[0]["reason"] == "overdue"

    async def test_a_row_matching_nothing_is_dropped_rather_than_guessed(self) -> None:
        """Unreachable through the query, which selects on exactly these two
        conditions. A sentence naming the wrong reason is worse than silence.
        """
        entries = await _fetch([_ticket(status="todo", due_at=None)])

        assert entries is None


class TestWhatTheDecisionReceives:
    async def test_each_entry_carries_what_the_prompt_and_the_bump_need(self) -> None:
        ticket = _ticket(due_at=NOW - timedelta(hours=2))

        entries = await _fetch([ticket])

        assert entries is not None
        assert entries[0]["id"] == str(ticket.id)
        assert entries[0]["title"] == "Réserver la salle"
        assert entries[0]["status"] == "todo"
        assert entries[0]["priority"] == "high"
        assert entries[0]["due_local"]

    async def test_a_ticket_with_no_due_date_says_so_rather_than_inventing_one(self) -> None:
        entries = await _fetch(
            [_ticket(status="waiting", status_changed_at=NOW - timedelta(days=5))]
        )

        assert entries is not None
        assert entries[0]["due_local"] is None

    async def test_the_date_is_rendered_in_the_persons_own_timezone(self) -> None:
        """Two accounts reading the same instant must not read the same clock
        face: a deadline at 23:00 in Paris is not 23:00 in Auckland."""
        moment = datetime(2026, 9, 9, 22, 30, tzinfo=UTC)

        with patch(f"{REPO}.list_nudge_worthy", AsyncMock(return_value=[_ticket(due_at=moment)])):
            paris = await fetch_workboard_context(
                MagicMock(), uuid.uuid4(), _user("Europe/Paris"), _settings()
            )
            auckland = await fetch_workboard_context(
                MagicMock(), uuid.uuid4(), _user("Pacific/Auckland"), _settings()
            )

        assert paris is not None and auckland is not None
        assert paris[0]["due_local"] != auckland[0]["due_local"]


class TestWhenTheSourceMustNotRun:
    async def test_a_switched_off_board_answers_nothing_and_queries_nothing(self) -> None:
        query = AsyncMock(return_value=[_ticket(due_at=NOW)])

        with patch(f"{REPO}.list_nudge_worthy", query):
            result = await fetch_workboard_context(
                MagicMock(), uuid.uuid4(), _user(), _settings(workboard_enabled=False)
            )

        assert result is None
        # Not merely « answered None »: a person who switched the board off
        # must stop paying for the query too.
        query.assert_not_awaited()

    async def test_an_empty_board_answers_None_rather_than_an_empty_list(self) -> None:
        """None is what the aggregator reads as « nothing to place »; an empty
        list would announce an empty section to the decision."""
        assert await _fetch([]) is None


class TestTheCapIsThePERSONS_setting:
    async def test_it_is_handed_to_the_query_rather_than_applied_after(self) -> None:
        query = AsyncMock(return_value=[])

        with patch(f"{REPO}.list_nudge_worthy", query):
            await fetch_workboard_context(
                MagicMock(), uuid.uuid4(), _user(), _settings(workboard_nudge_max_items=3)
            )

        assert query.await_args is not None
        assert query.await_args.kwargs["limit"] == 3

    async def test_the_three_windows_reach_the_query_as_instants(self) -> None:
        """The settings are hours and days; the query wants instants.

        Bounded on BOTH sides against the clock READ AROUND the call: a single
        bound compared to a `now` taken afterwards is off by however long the
        call took, which is the frozen-instant trap wearing a different hat.
        """
        query = AsyncMock(return_value=[])

        before = datetime.now(UTC)
        with patch(f"{REPO}.list_nudge_worthy", query):
            await fetch_workboard_context(
                MagicMock(),
                uuid.uuid4(),
                _user(),
                _settings(
                    workboard_nudge_due_hours=12,
                    workboard_nudge_waiting_hours=72,
                    workboard_nudge_cooldown_days=5,
                ),
            )
        after = datetime.now(UTC)

        assert query.await_args is not None
        kwargs = query.await_args.kwargs
        assert before + timedelta(hours=12) <= kwargs["due_before"] <= after + timedelta(hours=12)
        assert (
            before - timedelta(hours=72) <= kwargs["waiting_since"] <= after - timedelta(hours=72)
        )
        assert before - timedelta(days=5) <= kwargs["cooldown_before"] <= after - timedelta(days=5)


class TestTheCooldownStartsOnlyAfterDelivery:
    async def test_a_source_the_decision_ignored_burns_no_cooldown(self) -> None:
        """Exposing a ticket the decision chose not to mention must not silence
        it for the next two days — the same doctrine as the open loops."""
        bump = AsyncMock(return_value=0)
        metadata = {
            "sources_used": ["CALENDAR"],
            "workboard_ticket_ids": [str(uuid.uuid4())],
        }

        with patch(f"{REPO}.bump_nudged", bump):
            await _bump_used_workboard(MagicMock(), uuid.uuid4(), metadata)

        bump.assert_not_awaited()

    async def test_a_delivered_notification_stamps_the_tickets_it_named(self) -> None:
        bump = AsyncMock(return_value=2)
        first, second = uuid.uuid4(), uuid.uuid4()
        user_id = uuid.uuid4()
        metadata = {
            "sources_used": ["WORKBOARD"],
            "workboard_ticket_ids": [str(first), str(second)],
        }

        with patch(f"{REPO}.bump_nudged", bump):
            await _bump_used_workboard(MagicMock(), user_id, metadata)

        bump.assert_awaited_once()
        assert bump.await_args is not None
        assert bump.await_args.args[0] == [first, second]
        # The clause that stops an id from anywhere else touching a ticket.
        assert bump.await_args.kwargs["user_id"] == user_id

    async def test_a_malformed_id_is_skipped_rather_than_failing_the_bump(self) -> None:
        """The notification has already gone out: one unreadable id must not
        cost the cooldown of the ticket beside it."""
        bump = AsyncMock(return_value=1)
        good = uuid.uuid4()
        metadata = {
            "sources_used": ["WORKBOARD"],
            "workboard_ticket_ids": ["not-a-uuid", str(good)],
        }

        with patch(f"{REPO}.bump_nudged", bump):
            await _bump_used_workboard(MagicMock(), uuid.uuid4(), metadata)

        assert bump.await_args is not None
        assert bump.await_args.args[0] == [good]

    async def test_no_ids_at_all_touches_nothing(self) -> None:
        bump = AsyncMock(return_value=0)

        with patch(f"{REPO}.bump_nudged", bump):
            await _bump_used_workboard(MagicMock(), uuid.uuid4(), {"sources_used": ["WORKBOARD"]})

        bump.assert_not_awaited()


class TestATicketLIAHolds:
    async def test_its_deadline_is_LIAs_problem_not_the_persons(self) -> None:
        """Nagging the person about LIA's own backlog is noise: the sweep will
        run it, and if it cannot, the run's own failure notification says so.
        Unreachable through the query, which applies the same rule; pinned
        here so the two readers cannot drift apart."""
        entries = await _fetch([_ticket(due_at=NOW - timedelta(hours=3), assignee_kind="lia")])

        assert entries is None

    async def test_its_question_still_reaches_the_person(self) -> None:
        ticket = _ticket(
            status="waiting",
            status_changed_at=NOW - timedelta(days=3),
            assignee_kind="lia",
        )

        entries = await _fetch([ticket], said={ticket.id: "Which room, A or B?"})

        assert entries is not None
        assert entries[0]["reason"] == "waiting"

    async def test_a_result_awaiting_validation_surfaces_as_such(self) -> None:
        ticket = _ticket(
            status="validating",
            status_changed_at=NOW - timedelta(days=3),
            assignee_kind="lia",
        )

        entries = await _fetch([ticket], said={ticket.id: "Booked room B for Tuesday."})

        assert entries is not None
        assert entries[0]["reason"] == "validating"


class TestWhatLIASaidTravelsWithTheTicket:
    """A prompt asked to « say what it waits on » without the question would
    invent one. The run's own comment is quoted, bounded like the push."""

    async def test_a_waiting_ticket_quotes_LIAs_question(self) -> None:
        ticket = _ticket(status="waiting", status_changed_at=NOW - timedelta(days=3))

        entries = await _fetch([ticket], said={ticket.id: "Which room, A or B?"})

        assert entries is not None
        assert entries[0]["waiting_on"] == "Which room, A or B?"

    async def test_a_late_ticket_quotes_nothing(self) -> None:
        """An overdue ticket has no question to repeat — and the comments are
        not even read for it."""
        ticket = _ticket(due_at=NOW - timedelta(hours=2))
        comments = AsyncMock(return_value={ticket.id: "irrelevant"})

        with (
            patch(f"{REPO}.list_nudge_worthy", AsyncMock(return_value=[ticket])),
            patch(f"{REPO}.latest_lia_comments", comments),
        ):
            entries = await fetch_workboard_context(MagicMock(), uuid.uuid4(), _user(), _settings())

        assert entries is not None
        assert entries[0]["waiting_on"] is None
        comments.assert_not_awaited()

    async def test_the_quote_is_bounded_and_single_line(self) -> None:
        ticket = _ticket(status="waiting", status_changed_at=NOW - timedelta(days=3))
        long = "line one\nline two " + "x" * 500

        entries = await _fetch([ticket], said={ticket.id: long})

        assert entries is not None
        quote = entries[0]["waiting_on"]
        assert quote is not None
        assert "\n" not in quote
        assert quote.startswith("line one line two")
        assert len(quote) <= 200

    async def test_a_stopped_ticket_LIA_never_wrote_on_quotes_nothing(self) -> None:
        ticket = _ticket(status="waiting", status_changed_at=NOW - timedelta(days=3))

        entries = await _fetch([ticket], said={})

        assert entries is not None
        assert entries[0]["waiting_on"] is None
