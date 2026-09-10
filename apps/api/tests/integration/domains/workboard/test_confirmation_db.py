"""The confirmation on the ticket, against a real PostgreSQL server (lot 7).

Three things only the database can answer:

- the draft lands in the JSONB column, is read back whole, is cleared by an
  explicit None and left alone by a settle that says nothing;
- the owner's notes query really excludes a peer's and LIA's comments, keeps
  the latest N and returns them oldest first — on real rows, not on a
  rendered statement;
- the answer flow end to end: a ticket LIA handed back with a draft, the
  owner's comment, the handover to LIA, the row reloaded.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Any
from uuid import UUID

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from src.domains.users.models import User
from src.domains.workboard.constants import (
    ActorKind,
    AssigneeKind,
    RunOutcome,
    TicketPriority,
    TicketStatus,
)
from src.domains.workboard.models import WorkboardComment, WorkboardTicket
from src.domains.workboard.repository import KEEP_PENDING_ACTION, WorkboardRepository
from src.domains.workboard.schemas import TicketUpdate
from src.domains.workboard.service import WorkboardService

pytestmark = pytest.mark.integration

NOW = datetime(2026, 9, 9, 12, 0, tzinfo=UTC)
DRAFT: dict[str, Any] = {
    "draft_id": "draft_1",
    "draft_type": "tool_call",
    "draft_content": {"tool_name": "mcp_x_delete", "tool_args": {"target": "the archive"}},
    "tool_name": "mcp_x_delete",
    "question": "Je supprime « the archive » ?",
    "approved": False,
}


def _user(email: str, name: str) -> User:
    return User(
        email=email,
        hashed_password="x",
        is_active=True,
        is_verified=True,
        is_superuser=False,
        full_name=name,
    )


def _ticket(owner_id: UUID, **overrides: Any) -> WorkboardTicket:
    values: dict[str, Any] = {
        "owner_user_id": owner_id,
        "title": "Book the venue",
        "status": TicketStatus.TODO.value,
        "priority": TicketPriority.MEDIUM.value,
        "assignee_kind": AssigneeKind.LIA.value,
        "assignee_user_id": None,
        "position": 0,
        "created_by": ActorKind.USER.value,
        "status_changed_at": NOW,
        "run_attempts": 0,
        "run_count": 0,
        "nudge_count": 0,
    }
    values.update(overrides)
    return WorkboardTicket(**values)


def _comment(
    ticket_id: UUID,
    author: User | None,
    body: str,
    at: datetime,
    *,
    kind: str | None = None,
) -> WorkboardComment:
    """A comment as the service writes it: LIA's carry no author, a person's
    carry their kind — ``user`` for the owner, ``peer`` for a holder."""
    if author is None:
        author_kind = ActorKind.LIA.value
    else:
        author_kind = kind or ActorKind.USER.value
    return WorkboardComment(
        ticket_id=ticket_id,
        author_kind=author_kind,
        author_user_id=None if author is None else author.id,
        body=body,
        created_at=at,
    )


@pytest.fixture
async def owner(async_session: AsyncSession) -> User:
    user = _user("confirm-owner@example.org", "Owner")
    async_session.add(user)
    await async_session.commit()
    return user


@pytest.fixture
async def peer(async_session: AsyncSession) -> User:
    user = _user("confirm-peer@example.org", "Peer")
    async_session.add(user)
    await async_session.commit()
    return user


async def _reload(async_session: AsyncSession, ticket_id: UUID) -> WorkboardTicket:
    stored = await async_session.get(WorkboardTicket, ticket_id, populate_existing=True)
    assert stored is not None
    return stored


class TestTheDraftOnTheRow:
    async def test_a_settle_stores_the_draft_and_the_next_one_clears_it(
        self, async_session: AsyncSession, owner: User
    ) -> None:
        repo = WorkboardRepository(async_session)
        ticket = _ticket(owner.id)
        async_session.add(ticket)
        await async_session.commit()

        assert await repo.claim_ticket(ticket, run_id="r-1", now=NOW) is not None
        settled = await repo.settle_run(
            ticket_id=ticket.id,
            run_id="r-1",
            status=TicketStatus.CONFIRMING.value,
            outcome=RunOutcome.CONFIRMING.value,
            now=NOW + timedelta(minutes=1),
            hand_back=True,
            pending_action=DRAFT,
        )
        await async_session.commit()
        assert settled is True

        stored = await _reload(async_session, ticket.id)
        assert stored.status == TicketStatus.CONFIRMING.value
        assert stored.pending_action == DRAFT
        assert stored.assignee_kind == AssigneeKind.HUMAN.value

        # The person approved; the sweep took it and replayed it.
        stored.status = TicketStatus.TODO.value
        stored.assignee_kind = AssigneeKind.LIA.value
        stored.pending_action = {**DRAFT, "approved": True}
        await async_session.commit()
        assert (
            await repo.claim_ticket(stored, run_id="r-2", now=NOW + timedelta(hours=1)) is not None
        )
        await repo.settle_run(
            ticket_id=ticket.id,
            run_id="r-2",
            status=TicketStatus.VALIDATING.value,
            outcome=RunOutcome.SUCCESS.value,
            now=NOW + timedelta(hours=1, minutes=2),
            hand_back=True,
            pending_action=None,
        )
        await async_session.commit()
        assert (await _reload(async_session, ticket.id)).pending_action is None

    async def test_a_failed_settle_keeps_the_approval(
        self, async_session: AsyncSession, owner: User
    ) -> None:
        repo = WorkboardRepository(async_session)
        ticket = _ticket(owner.id, pending_action={**DRAFT, "approved": True})
        async_session.add(ticket)
        await async_session.commit()

        assert await repo.claim_ticket(ticket, run_id="r-1", now=NOW) is not None
        await repo.settle_run(
            ticket_id=ticket.id,
            run_id="r-1",
            status=TicketStatus.IN_PROGRESS.value,
            outcome=RunOutcome.FAILED.value,
            now=NOW + timedelta(minutes=1),
            error="workboard_run_failed: boom",
            pending_action=KEEP_PENDING_ACTION,
        )
        await async_session.commit()

        assert (await _reload(async_session, ticket.id)).pending_action == {
            **DRAFT,
            "approved": True,
        }


class TestTheOwnersNotesOnRealRows:
    async def test_only_the_owners_own_comments_since_the_instant_come_back(
        self, async_session: AsyncSession, owner: User, peer: User
    ) -> None:
        repo = WorkboardRepository(async_session)
        ticket = _ticket(owner.id, last_run_at=NOW)
        async_session.add(ticket)
        await async_session.flush()
        async_session.add_all(
            [
                _comment(ticket.id, owner, "before the run", NOW - timedelta(hours=1)),
                _comment(ticket.id, None, "Je supprime ?", NOW),
                _comment(
                    ticket.id, peer, "oui", NOW + timedelta(minutes=1), kind=ActorKind.PEER.value
                ),
                _comment(ticket.id, owner, "first", NOW + timedelta(minutes=2)),
                _comment(ticket.id, owner, "second", NOW + timedelta(minutes=3)),
                _comment(ticket.id, owner, "third", NOW + timedelta(minutes=4)),
            ]
        )
        await async_session.commit()

        notes = await repo.owner_notes_since(ticket.id, owner.id, since=NOW, limit=2)
        assert [note.body for note in notes] == ["second", "third"]

        everything = await repo.owner_notes_since(ticket.id, owner.id, since=None, limit=10)
        assert [note.body for note in everything] == ["before the run", "first", "second", "third"]

        # A peer's « oui » is never an answer, whoever asks: the kind is pinned
        # to ``user``, and a holder's comments are signed ``peer``.
        as_peer = await repo.owner_notes_since(ticket.id, peer.id, since=NOW, limit=10)
        assert [note.body for note in as_peer] == []


class TestTheAnswerFlow:
    async def _confirming_ticket(self, async_session: AsyncSession, owner: User) -> WorkboardTicket:
        ticket = _ticket(
            owner.id,
            status=TicketStatus.CONFIRMING.value,
            assignee_kind=AssigneeKind.HUMAN.value,
            pending_action=DRAFT,
            last_run_at=NOW,
            run_count=1,
        )
        async_session.add(ticket)
        await async_session.commit()
        return ticket

    async def test_an_approval_arms_the_replay(
        self, async_session: AsyncSession, owner: User
    ) -> None:
        ticket = await self._confirming_ticket(async_session, owner)
        async_session.add(_comment(ticket.id, owner, "Oui, vas-y", NOW + timedelta(minutes=5)))
        await async_session.commit()

        service = WorkboardService(async_session)
        await service.update(owner, ticket.id, TicketUpdate(assignee="lia"))
        await async_session.commit()

        stored = await _reload(async_session, ticket.id)
        assert stored.status == TicketStatus.TODO.value
        assert stored.assignee_kind == AssigneeKind.LIA.value
        assert stored.pending_action == {**DRAFT, "approved": True}
        assert stored.run_attempts == 0

    async def test_a_refusal_cancels_and_clears(
        self, async_session: AsyncSession, owner: User
    ) -> None:
        ticket = await self._confirming_ticket(async_session, owner)
        async_session.add(_comment(ticket.id, owner, "non merci", NOW + timedelta(minutes=5)))
        await async_session.commit()

        service = WorkboardService(async_session)
        await service.update(owner, ticket.id, TicketUpdate(assignee="lia"))
        await async_session.commit()

        stored = await _reload(async_session, ticket.id)
        assert stored.status == TicketStatus.DONE.value
        assert stored.assignee_kind == AssigneeKind.HUMAN.value
        assert stored.pending_action is None

    async def test_an_amendment_hands_over_with_the_draft_dropped(
        self, async_session: AsyncSession, owner: User
    ) -> None:
        ticket = await self._confirming_ticket(async_session, owner)
        async_session.add(
            _comment(ticket.id, owner, "Oui mais pas l'archive de 2024", NOW + timedelta(minutes=5))
        )
        await async_session.commit()

        service = WorkboardService(async_session)
        await service.update(owner, ticket.id, TicketUpdate(assignee="lia"))
        await async_session.commit()

        stored = await _reload(async_session, ticket.id)
        assert stored.status == TicketStatus.TODO.value
        assert stored.assignee_kind == AssigneeKind.LIA.value
        assert stored.pending_action is None
