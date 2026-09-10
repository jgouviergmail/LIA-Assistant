"""Workboard service: who may do what to a ticket, and the bounds it obeys.

**This is where the invariants the database cannot express live.** Proved on
a real PostgreSQL server, 2026-09-09 (``tests/integration/domains/workboard``): a CHECK
spanning two columns a foreign-key action can touch is violable whatever its
direction, because cascade order is not fixed and ``CHECK`` cannot be
``DEFERRABLE``. So « a peer assignment is authorised by an accepted
connection » is checked HERE, at every write, which is also D8's rule: a share
is re-resolved at execution time and never trusted from a stored row.

Rights, by the caller's relation to the row (spec §8):

- the **owner** may do anything, delete included;
- a peer **holder** may change status, priority and dates, comment, set their
  own follow flag, and hand the ticket back — never rewrite the owner's words,
  never delete, never pass it to a third person, and never hand it to their
  own LIA.

That last refusal is one rule seen from two sides: the instruction is the
owner's words, and running it unattended with the other account's tools would
put that account's data into a comment the owner reads.

Refusals are stable codes (:class:`WorkboardError`) through
``raise_invalid_input``; a ticket the caller cannot see is a neutral 404, so a
stranger cannot probe whether an id exists.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from uuid import UUID

import structlog
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.config import settings
from src.core.exceptions import raise_invalid_input, raise_not_found_or_unauthorized
from src.core.time_utils import now_utc
from src.domains.shared.text_normalization import fold_name
from src.domains.users.models import User
from src.domains.workboard.answers import Answer, classify_answer
from src.domains.workboard.board_queries import BoardFilters
from src.domains.workboard.constants import (
    NOTIFICATION_TASK_TYPE,
    ActorKind,
    AssigneeKind,
    TicketEventKind,
    TicketPriority,
    TicketStatus,
    WorkboardError,
)
from src.domains.workboard.models import WorkboardComment, WorkboardTicket, WorkboardTicketEvent
from src.domains.workboard.notifications import (
    WorkboardEvent,
    board_url,
    event_run_id,
    notification_body,
    notification_metadata,
    recipients_for,
    ticket_url,
)
from src.domains.workboard.repository import WorkboardRepository
from src.domains.workboard.schemas import BoardSummary, CommentCreate, TicketCreate, TicketUpdate
from src.domains.workboard.summary_queries import read_board_summary

logger = structlog.get_logger(__name__)

_STATUSES = frozenset(status.value for status in TicketStatus)
_PRIORITIES = frozenset(priority.value for priority in TicketPriority)


@dataclass(frozen=True)
class TicketBundle:
    """A ticket with everything its detail panel shows.

    Attributes:
        ticket: The row itself.
        children: Its sub-tickets, in board order.
        comments: Its thread, oldest first.
        events: Its history, oldest first.
    """

    ticket: WorkboardTicket
    children: list[WorkboardTicket]
    comments: list[WorkboardComment]
    events: list[WorkboardTicketEvent]


class WorkboardService:
    """Business rules of the board."""

    def __init__(self, db: AsyncSession) -> None:
        self.db = db
        self.repo = WorkboardRepository(db)

    # ---------------------------------------------------------------- helpers

    @staticmethod
    def _peers_enabled() -> bool:
        """Whether this instance runs the peers feature at all."""
        return bool(getattr(settings, "peers_enabled", False))

    async def _has_accepted_connection(self, user_a: UUID, user_b: UUID) -> bool:
        """Whether the two accounts are connected, right now.

        Re-resolved at every write rather than read from a stored column: the
        world moves between a ticket's creation and its next edit, and a stale
        authorisation is exactly what ADR-263's gate exists to refuse.

        Args:
            user_a: One side.
            user_b: The other side.

        Returns:
            True when an ACCEPTED connection joins them.
        """
        from src.domains.peers.repository import PeersRepository

        connections = await PeersRepository(self.db).list_accepted_for_user(user_a)
        return any(
            user_b in (connection.user_a_id, connection.user_b_id) for connection in connections
        )

    async def _visible_or_404(self, ticket_id: UUID, user_id: UUID) -> WorkboardTicket:
        """The ticket, if it is on this user's board.

        Args:
            ticket_id: The ticket.
            user_id: The caller.

        Returns:
            The row.

        Raises:
            ResourceNotFoundError: When it does not exist, or is not theirs —
                the same answer for both, so an id cannot be probed.
        """
        ticket = await self.repo.get_visible(ticket_id, user_id)
        if ticket is None:
            raise_not_found_or_unauthorized("ticket", ticket_id)
        return ticket

    @staticmethod
    def _actor_kind(ticket: WorkboardTicket, user_id: UUID) -> str:
        """How the caller signs an event or a comment on this ticket."""
        return ActorKind.USER.value if ticket.owner_user_id == user_id else ActorKind.PEER.value

    @staticmethod
    def _clean_title(title: str) -> str:
        """Validate a title against the published bound.

        Args:
            title: What the caller sent.

        Returns:
            The trimmed title.

        Raises:
            ValidationError: Blank, or longer than ``workboard_title_max_chars``.
        """
        cleaned = title.strip()
        if not cleaned:
            raise_invalid_input(WorkboardError.TITLE_REQUIRED.value)
        if len(cleaned) > settings.workboard_title_max_chars:
            raise_invalid_input(WorkboardError.TITLE_TOO_LONG.value)
        return cleaned

    @staticmethod
    def _clean_description(description: str | None) -> str | None:
        """Validate a description against the published bound.

        Args:
            description: What the caller sent, or None.

        Returns:
            The description, unchanged.

        Raises:
            ValidationError: Longer than ``workboard_description_max_chars``.
        """
        if description is not None and len(description) > settings.workboard_description_max_chars:
            raise_invalid_input(WorkboardError.DESCRIPTION_TOO_LONG.value)
        return description

    @staticmethod
    def _valid_status(status: str) -> str:
        """Refuse a column the board does not have.

        Args:
            status: The requested column.

        Returns:
            The status.

        Raises:
            ValidationError: When it is not a declared column.
        """
        if status not in _STATUSES:
            raise_invalid_input(WorkboardError.STATUS_INVALID.value)
        return status

    @staticmethod
    def _valid_priority(priority: str) -> str:
        """Refuse a priority the board does not have.

        Args:
            priority: The requested level.

        Returns:
            The priority.

        Raises:
            ValidationError: When it is not a declared level.
        """
        if priority not in _PRIORITIES:
            raise_invalid_input(WorkboardError.PRIORITY_INVALID.value)
        return priority

    @staticmethod
    def _check_dates(start_at: datetime | None, due_at: datetime | None) -> None:
        """Refuse a deadline that precedes its own start.

        Args:
            start_at: When work may start.
            due_at: When it is due.

        Raises:
            ValidationError: When the pair is inverted.
        """
        if start_at is not None and due_at is not None and due_at < start_at:
            raise_invalid_input(WorkboardError.DATES_INVERTED.value)

    async def _resolve_assignment(
        self, owner_id: UUID, assignee: str | None, assignee_user_id: UUID | None
    ) -> tuple[str, UUID | None]:
        """Turn a request into the stored ``(kind, holder)`` pair.

        NULL is « the owner holds it », so naming the owner — by ``me`` or by
        their own id — stores NULL rather than the id. That single convention
        is what lets a departing peer release a ticket through a foreign-key
        action instead of a maintenance job.

        Args:
            owner_id: The board's owner.
            assignee: ``me`` | ``lia`` | None.
            assignee_user_id: A peer's id, or None.

        Returns:
            The kind and the holder to store.

        Raises:
            ValidationError: Peers disabled, or no accepted connection.
        """
        if assignee_user_id is not None and assignee_user_id != owner_id:
            if not self._peers_enabled():
                raise_invalid_input(WorkboardError.PEERS_DISABLED.value)
            if not await self._has_accepted_connection(owner_id, assignee_user_id):
                raise_invalid_input(WorkboardError.ASSIGNEE_NOT_CONNECTED.value)
            return AssigneeKind.HUMAN.value, assignee_user_id
        if assignee == "lia":
            return AssigneeKind.LIA.value, None
        return AssigneeKind.HUMAN.value, None

    async def resolve_connected_user_id(self, owner_id: UUID, name: str) -> UUID:
        """The account a NAME refers to, among this user's connections.

        The chat says « donne ce ticket à Marie »; the board stores an id. The
        resolution lives HERE rather than in the tool because the service
        already owns who may hold a ticket, and a tool deciding it again would
        be a second authority on the same question.

        Matched on the FOLDED name (``fold_name`` is the one authority on name
        identity, ADR-185), and only among ACCEPTED connections: the discovery
        directory is not an address book, and a name that matches nobody the
        user is connected to is « not connected », not « unknown person ».

        Ambiguity is REFUSED rather than guessed at: two connections called
        Marie make handing the ticket to the wrong one worse than asking.

        Args:
            owner_id: The board's owner.
            name: The name as the person said it.

        Returns:
            The connected account's id.

        Raises:
            ValidationError: Peers are off, nobody matches, or several do.
        """
        from src.domains.peers.repository import PeersRepository

        if not self._peers_enabled():
            raise_invalid_input(WorkboardError.PEERS_DISABLED.value)
        repo = PeersRepository(self.db)
        connections = await repo.list_accepted_for_user(owner_id)
        peer_ids = [(c.user_b_id if c.user_a_id == owner_id else c.user_a_id) for c in connections]
        if not peer_ids:
            raise_invalid_input(WorkboardError.ASSIGNEE_NOT_CONNECTED.value)
        rows = (
            await self.db.execute(select(User.id, User.full_name).where(User.id.in_(peer_ids)))
        ).all()
        needle = fold_name(name)
        matches = [
            UUID(str(uid)) for uid, full_name in rows if fold_name(full_name or "") == needle
        ]
        if len(matches) == 1:
            return matches[0]
        if not matches:
            raise_invalid_input(WorkboardError.ASSIGNEE_NOT_CONNECTED.value)
        # `raise_invalid_input` is typed `NoReturn`, so this closes the
        # function: a line after it would be unreachable, and the sibling
        # `resolve_reference` ends the same way.
        raise_invalid_input(WorkboardError.AMBIGUOUS_REFERENCE.value)

    async def _event(
        self,
        ticket: WorkboardTicket,
        actor: User | None,
        kind: TicketEventKind,
        payload: dict[str, object] | None = None,
    ) -> WorkboardTicketEvent:
        """Append one history entry.

        Args:
            ticket: The ticket it happened to.
            actor: Who did it; None when LIA did.
            kind: What happened.
            payload: Bounded facts, never free text.

        Returns:
            The flushed event row, whose id names the act.
        """
        return await self.repo.add_event(
            ticket_id=ticket.id,
            actor_kind=(
                ActorKind.LIA.value if actor is None else self._actor_kind(ticket, actor.id)
            ),
            actor_user_id=None if actor is None else actor.id,
            kind=kind.value,
            payload=payload,
        )

    # ----------------------------------------------------------------- create

    async def create(self, actor: User, data: TicketCreate) -> WorkboardTicket:
        """Create a ticket on the caller's board.

        Args:
            actor: The owner-to-be.
            data: The request.

        Returns:
            The created row, flushed — the caller owns the commit.

        Raises:
            ValidationError: Any bound or assignment rule.
            ResourceNotFoundError: An unknown or invisible parent.
        """
        title = self._clean_title(data.title)
        description = self._clean_description(data.description)
        status = self._valid_status(data.status)
        priority = self._valid_priority(data.priority)
        self._check_dates(data.start_at, data.due_at)

        if await self.repo.count_owned(actor.id) >= settings.workboard_max_tickets_per_user:
            raise_invalid_input(WorkboardError.TOO_MANY_TICKETS.value)

        if data.parent_id is not None:
            await self._check_parent(actor, data.parent_id)

        kind, holder = await self._resolve_assignment(
            actor.id, data.assignee, data.assignee_user_id
        )
        ticket = await self.repo.create(
            {
                "owner_user_id": actor.id,
                "parent_id": data.parent_id,
                "title": title,
                "description": description,
                "status": status,
                "priority": priority,
                "start_at": data.start_at,
                "due_at": data.due_at,
                "assignee_kind": kind,
                "assignee_user_id": holder,
                "execution_mode": data.execution_mode,
                "position": await self.repo.next_position(actor.id, status),
                "follow_owner": data.follow,
                "follow_assignee": False,
                "created_by": ActorKind.USER.value,
                "status_changed_at": now_utc(),
            }
        )
        await self._event(ticket, actor, TicketEventKind.CREATED, {"status": status})
        logger.info(
            "workboard_ticket_created",
            ticket_id=str(ticket.id),
            owner_id=str(actor.id),
            assignee_kind=kind,
            has_parent=data.parent_id is not None,
        )
        return ticket

    async def _check_parent(self, actor: User, parent_id: UUID) -> None:
        """Refuse a parent that is not the caller's, or already a child.

        Args:
            actor: The caller.
            parent_id: The proposed parent.

        Raises:
            ValidationError: Not owned, already a child, or at its cap.
            ResourceNotFoundError: Unknown or invisible.
        """
        parent = await self._visible_or_404(parent_id, actor.id)
        if parent.owner_user_id != actor.id:
            raise_invalid_input(WorkboardError.PARENT_NOT_OWNED.value)
        if parent.parent_id is not None:
            raise_invalid_input(WorkboardError.DEPTH_EXCEEDED.value)
        if await self.repo.count_children(parent.id) >= settings.workboard_max_children_per_ticket:
            raise_invalid_input(WorkboardError.TOO_MANY_CHILDREN.value)

    # ------------------------------------------------------------------ reads

    async def get(self, actor: User, ticket_id: UUID) -> TicketBundle:
        """One ticket with its children, its thread and its history.

        Args:
            actor: The reader.
            ticket_id: The ticket.

        Returns:
            The bundle.

        Raises:
            ResourceNotFoundError: Unknown or not on their board.
        """
        ticket = await self._visible_or_404(ticket_id, actor.id)
        return TicketBundle(
            ticket=ticket,
            children=await self.repo.list_children(ticket.id),
            comments=await self.repo.list_comments(ticket.id),
            events=await self.repo.list_events(ticket.id),
        )

    async def board(
        self, actor: User, filters: BoardFilters, *, limit: int, offset: int
    ) -> tuple[list[WorkboardTicket], int, dict[str, int]]:
        """One page of the board, its exact total, and its column counts.

        Args:
            actor: The reader.
            filters: What they asked for.
            limit: Page size.
            offset: Page offset.

        Returns:
            The rows, the total and one exact count per column.
        """
        rows, total = await self.repo.list_board(actor.id, filters, limit=limit, offset=offset)
        return rows, total, await self.repo.counts_by_status(actor.id, filters)

    async def needs_me(
        self, actor: User, *, limit: int, offset: int
    ) -> tuple[list[WorkboardTicket], int]:
        """Tickets waiting on this account, plus the late ones on its board.

        Args:
            actor: The reader.
            limit: Page size.
            offset: Page offset.

        Returns:
            The page and the exact total.
        """
        return await self.repo.needs_me(actor.id, now_utc(), limit=limit, offset=offset)

    async def summary(self, actor: User) -> BoardSummary:
        """The board at a glance, with the caps this instance enforces (lot 18).

        Args:
            actor: The reader.

        Returns:
            Every figure an aggregate over its whole set, the caps published.
        """
        figures = await read_board_summary(self.repo, actor.id, now_utc())
        return BoardSummary(
            total=sum(figures.counts_by_status.values()),
            counts_by_status=figures.counts_by_status,
            overdue=figures.overdue,
            held_by_lia=figures.held_by_lia,
            needs_me=figures.needs_me,
            owned=figures.owned,
            max_tickets=settings.workboard_max_tickets_per_user,
            max_runs_per_ticket=settings.workboard_max_runs_per_ticket,
            runs_total=figures.runs_total,
            tokens_in=figures.tokens_in,
            tokens_out=figures.tokens_out,
            tokens_cache=figures.tokens_cache,
            google_requests=figures.google_requests,
            cost_eur=float(figures.cost_eur),
        )

    # ----------------------------------------------------------------- update

    async def update(self, actor: User, ticket_id: UUID, data: TicketUpdate) -> WorkboardTicket:
        """Apply a partial update under the caller's rights.

        Args:
            actor: The caller.
            ticket_id: The ticket.
            data: What to change; absent means unchanged.

        Returns:
            The updated row, not yet committed.

        Raises:
            ValidationError: A bound, a right, or an assignment rule.
            ResourceNotFoundError: Unknown or not on their board.
        """
        ticket = await self._visible_or_404(ticket_id, actor.id)
        is_owner = ticket.owner_user_id == actor.id

        self._apply_words(ticket, data, is_owner=is_owner)
        # The mode is the OWNER's to set — LIA runs on their account, and a
        # holder choosing the loop would be spending somebody else's quota. No
        # event: it changes nothing about the work, only how the next run is
        # driven, and a history line per toggle would bury the ones that matter.
        if data.execution_mode is not None and is_owner:
            ticket.execution_mode = data.execution_mode
        await self._apply_priority(ticket, actor, data)
        await self._apply_dates(ticket, actor, data)

        if data.assignee is not None or data.assignee_user_id is not None:
            answer = await self._answer_on_the_ticket(ticket, actor, data)
            if answer is not Answer.REFUSE:
                await self._reassign(
                    ticket,
                    actor,
                    data.assignee,
                    data.assignee_user_id,
                    reason=answer.value if answer is not None else None,
                )
        if data.status is not None and data.status != ticket.status:
            await self._transition(ticket, actor, self._valid_status(data.status))
        await self._apply_follow(ticket, actor, data, is_owner=is_owner)
        return ticket

    def _apply_words(self, ticket: WorkboardTicket, data: TicketUpdate, *, is_owner: bool) -> None:
        """Set the title and the description — the owner's words, theirs alone.

        Args:
            ticket: The row being edited.
            data: The request.
            is_owner: Whether the caller owns the ticket.

        Raises:
            ValidationError: A holder editing them, or a bound.
        """
        if data.title is None and data.description is None:
            return
        if not is_owner:
            raise_invalid_input(WorkboardError.PEER_CANNOT_EDIT_FIELD.value)
        if data.title is not None:
            ticket.title = self._clean_title(data.title)
        if data.description is not None:
            ticket.description = self._clean_description(data.description)

    async def _apply_priority(
        self, ticket: WorkboardTicket, actor: User, data: TicketUpdate
    ) -> None:
        """Change the priority, and record the move.

        Args:
            ticket: The row being edited.
            actor: The caller.
            data: The request.

        Raises:
            ValidationError: A level the board does not have.
        """
        if data.priority is None or data.priority == ticket.priority:
            return
        previous = ticket.priority
        ticket.priority = self._valid_priority(data.priority)
        await self._event(
            ticket,
            actor,
            TicketEventKind.PRIORITY_CHANGED,
            {"from": previous, "to": ticket.priority},
        )

    async def _apply_follow(
        self, ticket: WorkboardTicket, actor: User, data: TicketUpdate, *, is_owner: bool
    ) -> None:
        """Set the CALLER's own follow flag, never the other side's.

        Args:
            ticket: The row being edited.
            actor: The caller.
            data: The request.
            is_owner: Whether the caller owns the ticket.
        """
        if data.follow is None:
            return
        if is_owner:
            ticket.follow_owner = data.follow
        else:
            ticket.follow_assignee = data.follow
        await self._event(ticket, actor, TicketEventKind.FOLLOW_CHANGED, {"to": data.follow})

    async def _apply_dates(self, ticket: WorkboardTicket, actor: User, data: TicketUpdate) -> None:
        """Set or clear the two dates, validating the pair that results.

        Args:
            ticket: The row being edited.
            actor: The caller.
            data: The request.

        Raises:
            ValidationError: When the resulting pair is inverted.
        """
        start_at = None if data.clear_start_at else (data.start_at or ticket.start_at)
        due_at = None if data.clear_due_at else (data.due_at or ticket.due_at)
        if (start_at, due_at) == (ticket.start_at, ticket.due_at):
            return
        self._check_dates(start_at, due_at)
        previous_start, previous_due = ticket.start_at, ticket.due_at
        ticket.start_at, ticket.due_at = start_at, due_at
        # The history is read to understand what happened, so it carries the
        # two values rather than the bare fact that something moved. ISO
        # strings: the reader's own timezone is applied where it is DISPLAYED,
        # never frozen into the log.
        await self._event(
            ticket,
            actor,
            TicketEventKind.DATES_CHANGED,
            {
                "from_start": previous_start.isoformat() if previous_start else None,
                "to_start": start_at.isoformat() if start_at else None,
                "from_due": previous_due.isoformat() if previous_due else None,
                "to_due": due_at.isoformat() if due_at else None,
            },
        )

    async def _answer_on_the_ticket(
        self, ticket: WorkboardTicket, actor: User, data: TicketUpdate
    ) -> Answer | None:
        """Read the person's answer when they hand a ticket LIA is waiting on back to LIA.

        The ticket is « à confirmer » and the owner hands it to LIA: their
        LATEST note since LIA's last run is the answer (lot 7). An approval
        keeps the draft on the ticket, marked approved, for the sweep to
        replay; a refusal cancels the ticket and leaves it with the person; an
        amendment clears the draft, and the notes reach the next brief.

        Args:
            ticket: The row, possibly not in that situation at all.
            actor: The caller.
            data: The update, possibly not a handover to LIA at all.

        Returns:
            The answer read, or None when the update is not that gesture —
            the caller then reassigns as it always did.

        Raises:
            ValidationError: No note to read, or the ticket has no runs left.
        """
        if ticket.status != TicketStatus.CONFIRMING.value or data.assignee != "lia":
            return None
        if not ticket.pending_action:
            # A ticket a person PARKED in « à confirmer » carries no question:
            # handing it to LIA is the ordinary handover.
            return None
        if ticket.owner_user_id != actor.id:
            # A peer handing it to LIA is refused further down, as it always was.
            return None
        notes = await self.repo.owner_notes_since(
            ticket.id, ticket.owner_user_id, since=ticket.last_run_at, limit=1
        )
        if not notes:
            raise_invalid_input(WorkboardError.ANSWER_REQUIRED.value)
        return await self._apply_answer(ticket, actor, notes[-1].body)

    async def _apply_answer(self, ticket: WorkboardTicket, actor: User, text: str) -> Answer:
        """Read what the person answered, and move the ticket accordingly.

        The ONE place the three verdicts become a column, so the comment door
        and the hand-over door cannot drift apart.

        Args:
            ticket: The ticket waiting on a confirmation.
            actor: The owner, who is the only one whose words count here.
            text: What they wrote.

        Returns:
            The verdict, for the caller to hand the ticket over on.

        Raises:
            ValidationError: The ticket has no runs left to spend.
        """
        answer = classify_answer(text)
        pending = ticket.pending_action or {}
        if answer is Answer.REFUSE:
            # « Terminé », not « Annulé » (which no longer exists): the ticket
            # is closed, and the history's ``reason`` says the person refused.
            await self._transition(ticket, actor, TicketStatus.DONE.value, reason=answer.value)
        else:
            if ticket.run_count >= settings.workboard_max_runs_per_ticket:
                raise_invalid_input(WorkboardError.MAX_RUNS_REACHED.value)
            await self._transition(ticket, actor, TicketStatus.TODO.value, reason=answer.value)
            if answer is Answer.APPROVE and pending:
                # A NEW dict (the JSONB rule): the transition cleared the column
                # and the approval is what the sweep replays.
                ticket.pending_action = {**pending, "approved": True}
            # A person's explicit answer is a FRESH run (the « run now » rule).
            ticket.run_attempts = 0
            ticket.run_not_before = None
        logger.info(
            "workboard_confirmation_answered", ticket_id=str(ticket.id), answer=answer.value
        )
        return answer

    async def _reassign(
        self,
        ticket: WorkboardTicket,
        actor: User,
        assignee: str | None,
        assignee_user_id: UUID | None,
        *,
        reason: str | None = None,
    ) -> None:
        """Hand the ticket to somebody else, under the caller's rights.

        Args:
            ticket: The row.
            actor: The caller.
            assignee: ``me`` | ``lia`` | None.
            assignee_user_id: A peer's id, or None.
            reason: Why, when the handover is the person's answer to a
                confirmation (``approve`` | ``amend``); the history shows it.

        Raises:
            ValidationError: A peer overreaching, or a cross-account delegation.
        """
        if ticket.owner_user_id != actor.id:
            # A holder may only hand the ticket BACK.
            if assignee == "lia":
                raise_invalid_input(WorkboardError.CROSS_ACCOUNT_DELEGATION.value)
            if assignee_user_id not in (None, ticket.owner_user_id):
                raise_invalid_input(WorkboardError.PEER_CANNOT_REASSIGN.value)
            kind, holder = AssigneeKind.HUMAN.value, None
        else:
            # LIA runs on the HOLDER's account. Delegating a ticket somebody
            # else holds would run the owner's instruction with that account's
            # tools — the same refusal as a peer delegating to their own LIA.
            if assignee == "lia" and ticket.assignee_user_id is not None:
                raise_invalid_input(WorkboardError.CROSS_ACCOUNT_DELEGATION.value)
            kind, holder = await self._resolve_assignment(
                ticket.owner_user_id, assignee, assignee_user_id
            )

        previous = (ticket.assignee_kind, ticket.assignee_user_id)
        ticket.assignee_kind, ticket.assignee_user_id = kind, holder
        # The next holder never inherits somebody else's subscription.
        ticket.follow_assignee = False
        event = await self._event(
            ticket,
            actor,
            TicketEventKind.ASSIGNED,
            {
                "from_kind": previous[0],
                "from_user": str(previous[1]) if previous[1] else None,
                "to_kind": kind,
                "to_user": str(holder) if holder else None,
                **({"reason": reason} if reason else {}),
            },
        )
        await self._announce_assignment(ticket, actor, event_id=event.id)

    async def _announce_assignment(
        self, ticket: WorkboardTicket, actor: User, *, event_id: UUID
    ) -> None:
        """Tell the new holder, because nothing else can.

        The follow flag cannot cover this one: nobody subscribes to a ticket
        they do not yet know they hold. It reaches the new holder alone — the
        person who handed it over already knows.

        Sent through the seam (``domains/shared/proactive_sink``) and never by
        importing the dispatcher: ``agents`` imports this package, and the
        dispatcher imports ``agents``.

        Best-effort by contract, and OUTSIDE the transaction's success: a
        notification that could not leave must not undo an assignment the
        person asked for and the board already holds.

        Args:
            ticket: The reassigned row.
            actor: Who reassigned it.
            event_id: The ASSIGNED event — the run the register row is filed under.
        """
        from src.domains.shared.proactive_sink import send_proactive_notification

        recipients = recipients_for(WorkboardEvent.ASSIGNED, ticket, actor_user_id=actor.id)
        for user_id in recipients:
            recipient = await self.db.get(User, user_id)
            if recipient is None:
                continue
            language = getattr(recipient, "language", None) or settings.default_language
            await send_proactive_notification(
                db=self.db,
                user=recipient,
                content=notification_body(WorkboardEvent.ASSIGNED, ticket, language=language),
                task_type=NOTIFICATION_TASK_TYPE,
                target_id=str(ticket.id),
                metadata=notification_metadata(
                    WorkboardEvent.ASSIGNED,
                    ticket,
                    board_url=board_url(),
                    ticket_url=ticket_url(ticket),
                ),
                # The act's own run: the ASSIGNED event that caused this
                # notification, a row anyone can join. A second handover is a
                # second event, so it is never lost as a replay of the first.
                run_id=event_run_id(event_id),
                occurrence=WorkboardEvent.ASSIGNED.value,
            )

    async def _transition(
        self,
        ticket: WorkboardTicket,
        actor: User | None,
        status: str,
        *,
        reason: str | None = None,
    ) -> None:
        """Move a ticket to another column, at the end of it.

        Leaving « à confirmer » drops the draft the ticket carried: whatever
        the destination, the question is no longer asked (lot 7). An approval
        is written back by the caller AFTER this, as a new dict.

        Args:
            ticket: The row.
            actor: The caller, or None when LIA moved it.
            status: The destination column.
            reason: Why, when the move is the person's answer to a
                confirmation (``approve`` | ``refuse`` | ``amend``).
        """
        previous = ticket.status
        ticket.status = status
        ticket.status_changed_at = now_utc()
        ticket.position = await self.repo.next_position(ticket.owner_user_id, status)
        if previous == TicketStatus.CONFIRMING.value:
            ticket.pending_action = None
        await self._event(
            ticket,
            actor,
            TicketEventKind.STATUS_CHANGED,
            {"from": previous, "to": status, **({"reason": reason} if reason else {})},
        )

    async def move(
        self, actor: User, ticket_id: UUID, status: str, position: int
    ) -> WorkboardTicket:
        """The drag-and-drop write: a column, and a place in it.

        Positions belong to the OWNER's board, so a holder moving a ticket
        renumbers the OWNER's column, never one of their own.

        The consequence a client must respect: a peer's board carries tickets
        from several owners, so an index that means something there means
        nothing in any single owner's column. A peer changes a ticket's COLUMN;
        its rank inside that column is its owner's to arrange.

        Args:
            actor: The caller.
            ticket_id: The ticket.
            status: The destination column.
            position: Where in it, 0 first.

        Returns:
            The moved row, not yet committed.

        Raises:
            ValidationError: An unknown column.
            ResourceNotFoundError: Unknown or not on their board.
        """
        ticket = await self._visible_or_404(ticket_id, actor.id)
        status = self._valid_status(status)
        if ticket.status != status:
            await self._transition(ticket, actor, status)

        ids = [
            other
            for other in await self.repo.list_column_ids(ticket.owner_user_id, status)
            if other != ticket.id
        ]
        ids.insert(max(0, min(position, len(ids))), ticket.id)
        await self.repo.renumber_column(ticket.owner_user_id, status, ids)
        ticket.position = ids.index(ticket.id)
        return ticket

    async def run_now(self, actor: User, ticket_id: UUID) -> WorkboardTicket:
        """Offer a LIA-assigned ticket to the next sweep.

        Args:
            actor: The caller.
            ticket_id: The ticket.

        Returns:
            The armed row, not yet committed.

        Raises:
            ValidationError: Not assigned to LIA, or past the runs cap.
            ResourceNotFoundError: Unknown or not on their board.
        """
        ticket = await self._visible_or_404(ticket_id, actor.id)
        if ticket.assignee_kind != AssigneeKind.LIA.value:
            raise_invalid_input(WorkboardError.RUN_NOW_REQUIRES_LIA.value)
        if ticket.run_count >= settings.workboard_max_runs_per_ticket:
            raise_invalid_input(WorkboardError.MAX_RUNS_REACHED.value)
        ticket.start_at = None
        ticket.run_not_before = None
        # A person's explicit ask is a FRESH run. Without this a ticket the
        # reaper released three times stays under the attempts cap for ever,
        # and « Lancer maintenant » would move it to todo and change nothing.
        ticket.run_attempts = 0
        if ticket.status != TicketStatus.TODO.value:
            await self._transition(ticket, actor, TicketStatus.TODO.value)
        logger.info("workboard_run_requested", ticket_id=str(ticket.id))
        return ticket

    async def comment(self, actor: User, ticket_id: UUID, data: CommentCreate) -> WorkboardComment:
        """Append a comment to a ticket.

        Args:
            actor: The caller.
            ticket_id: The ticket.
            data: The comment.

        Returns:
            The flushed row.

        Raises:
            ValidationError: Blank, or over the published bound.
            ResourceNotFoundError: Unknown or not on their board.
        """
        ticket = await self._visible_or_404(ticket_id, actor.id)
        body = data.body.strip()
        if not body:
            raise_invalid_input(WorkboardError.COMMENT_REQUIRED.value)
        if len(body) > settings.workboard_comment_max_chars:
            raise_invalid_input(WorkboardError.COMMENT_TOO_LONG.value)
        comment = await self.repo.add_comment(
            ticket_id=ticket.id,
            author_kind=self._actor_kind(ticket, actor.id),
            author_user_id=actor.id,
            body=body,
        )
        await self._answer_by_comment(ticket, actor, body)
        return comment

    async def _answer_by_comment(self, ticket: WorkboardTicket, actor: User, body: str) -> None:
        """A comment on a ticket LIA is waiting on IS the answer (2026-09-09).

        The person wrote what they think; asking them to hand the ticket back
        as well is a second gesture for one decision, and a ticket left in « à
        confirmer » with an answer already on it is the exact shape of work
        that never moves. So the comment classifies, moves the ticket, and
        hands it to LIA — for an approval and for an amendment alike, since
        both need LIA to run again. A refusal closes it and keeps it here.

        Silent by construction outside that situation: an ordinary comment on
        an ordinary ticket changes nothing.

        Args:
            ticket: The ticket just commented on.
            actor: Who commented.
            body: What they wrote.
        """
        if (
            ticket.status != TicketStatus.CONFIRMING.value
            or not ticket.pending_action
            or ticket.owner_user_id != actor.id
        ):
            return
        answer = await self._apply_answer(ticket, actor, body)
        if answer is not Answer.REFUSE:
            await self._reassign(ticket, actor, "lia", None, reason=answer.value)

    async def deletable(self, actor: User, ticket_id: UUID) -> tuple[WorkboardTicket, int]:
        """The ticket, once the caller is allowed to delete it, and its steps.

        Shared by the deletion and by the chat tool that ASKS before deleting:
        a person must be refused before being handed a confirmation card they
        could only ever have refused — and the rule must live once.

        Args:
            actor: The caller.
            ticket_id: The ticket.

        Returns:
            The row and how many steps hang off it.

        Raises:
            ValidationError: A holder trying to delete somebody else's ticket.
            ResourceNotFoundError: Unknown or not on their board.
        """
        ticket = await self._visible_or_404(ticket_id, actor.id)
        if ticket.owner_user_id != actor.id:
            raise_invalid_input(WorkboardError.PEER_CANNOT_DELETE.value)
        return ticket, await self.repo.count_children(ticket.id)

    async def delete(self, actor: User, ticket_id: UUID) -> int:
        """Delete a ticket and its children — the owner only.

        Args:
            actor: The caller.
            ticket_id: The ticket.

        Returns:
            How many rows go, the ticket included, so the confirmation can say
            what it takes rather than implying one.

        Raises:
            ValidationError: A holder trying to delete somebody else's ticket.
            ResourceNotFoundError: Unknown or not on their board.
        """
        ticket, children = await self.deletable(actor, ticket_id)
        await self.repo.delete(ticket)
        logger.info("workboard_ticket_deleted", ticket_id=str(ticket.id), children=children)
        return children + 1

    async def release_pair(self, user_a: UUID, user_b: UUID) -> list[WorkboardTicket]:
        """Hand back every ticket the two accounts share, both directions.

        Called when a connection is removed or blocked. The PAIR is the
        connection — ``peer_connections`` holds one row per pair for life — so
        no ticket stores a connection id to go stale.

        Args:
            user_a: One side.
            user_b: The other side.

        Returns:
            The tickets released, not yet committed.
        """
        released: list[WorkboardTicket] = []
        for owner_id, holder_id in ((user_a, user_b), (user_b, user_a)):
            for ticket in await self.repo.list_held_between(owner_id, holder_id):
                ticket.assignee_kind = AssigneeKind.HUMAN.value
                ticket.assignee_user_id = None
                ticket.follow_assignee = False
                await self._event(
                    ticket,
                    None,
                    TicketEventKind.ASSIGNED,
                    {"to_kind": AssigneeKind.HUMAN.value, "reason": "connection_removed"},
                )
                released.append(ticket)
        if released:
            logger.info("workboard_tickets_released", tickets=len(released))
        return released

    async def resolve_reference(self, user_id: UUID, reference: str) -> WorkboardTicket:
        """A ticket named by id, or by a UNIQUE folded title.

        Ambiguity is refused rather than guessed at: a false positive hands one
        ticket's fate to a question about another (ADR-269's rule about the
        debrief directory, applied to a board).

        Args:
            user_id: The caller.
            reference: An id, or what they called the ticket.

        Returns:
            The one ticket it names.

        Raises:
            ValidationError: Several tickets carry that title.
            ResourceNotFoundError: None does, or the id is not theirs.
        """
        try:
            ticket_id = UUID(reference)
        except ValueError:
            ticket_id = None
        if ticket_id is not None:
            # A well-formed id that names nothing visible is a 404, never a
            # title search: falling back would tell a stranger an id exists.
            return await self._visible_or_404(ticket_id, user_id)

        matches = await self.repo.find_by_title(user_id, reference)
        if len(matches) == 1:
            return matches[0]
        if not matches:
            raise_not_found_or_unauthorized("ticket")
        raise_invalid_input(WorkboardError.AMBIGUOUS_REFERENCE.value)
