"""Tickets waiting on the listener: the one reason each waits, lateness in their own days."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta, timezone
from uuid import UUID

import pytest

from src.domains.radio.facts import FactKind, Sensitivity
from src.domains.radio.readers.tickets import TicketLine, ticket_drafts

pytestmark = pytest.mark.unit

NOW = datetime(2026, 9, 26, 7, 0, tzinfo=UTC)
PLUS_TWO = timezone(timedelta(hours=2))


def ticket(
    n: int, *, status: str = "todo", priority: str = "medium", due: datetime | None
) -> TicketLine:
    return TicketLine(
        id=UUID(int=n), title=f"Ticket {n}", status=status, priority=priority, due_at=due
    )


def test_it_says_why_each_ticket_waits_on_the_listener() -> None:
    drafts = ticket_drafts(
        [
            ticket(1, status="confirming", due=None),
            ticket(2, status="waiting", due=None),
            ticket(3, due=NOW - timedelta(days=3), priority="urgent"),
        ],
        now=NOW,
        tz=UTC,
    )
    assert [draft.text for draft in drafts] == [
        'Ticket "Ticket 1": LIA is waiting for the listener to confirm an action',
        'Ticket "Ticket 2": LIA asked the listener a question and is waiting for the answer',
        'Ticket "Ticket 3" was due 3 days ago (urgent)',
    ]
    assert {draft.kind for draft in drafts} == {FactKind.TICKET}
    assert {draft.sensitivity for draft in drafts} == {Sensitivity.PERSONAL}


def test_lateness_is_counted_in_the_listener_s_own_days() -> None:
    """23:30 UTC yesterday is 01:30 TODAY two hours east: due earlier today, not yesterday."""
    due = datetime(2026, 9, 25, 23, 30, tzinfo=UTC)
    [east] = ticket_drafts([ticket(4, due=due)], now=NOW, tz=PLUS_TWO)
    [west] = ticket_drafts([ticket(4, due=due)], now=NOW, tz=UTC)
    assert east.text.endswith("was due earlier today")
    assert west.text.endswith("was due yesterday")


def test_a_ticket_that_changes_reason_may_be_heard_again() -> None:
    [late] = ticket_drafts([ticket(5, due=NOW - timedelta(days=1))], now=NOW, tz=UTC)
    [asking] = ticket_drafts([ticket(5, status="waiting", due=None)], now=NOW, tz=UTC)
    assert late.key != asking.key
    assert late.key.startswith(f"ticket:{UUID(int=5)}")


def test_a_ticket_closed_today_is_done_on_the_listener_s_clock() -> None:
    from src.domains.radio.personal import JournalPart
    from src.domains.radio.readers.tickets import ClosedTicket, closed_ticket_drafts

    closed = ClosedTicket(
        id=UUID(int=8), title="Renew the lease", closed_at=NOW + timedelta(hours=7)
    )
    [draft] = closed_ticket_drafts([closed], tz=PLUS_TWO)
    assert draft.text == 'Ticket "Renew the lease" was closed today at 16:00'
    assert (draft.kind, draft.sensitivity, draft.part) == (
        FactKind.TICKET,
        Sensitivity.PERSONAL,
        JournalPart.DONE,
    )
    assert draft.key == f"done:ticket:{UUID(int=8)}"  # never the waiting ticket's key
