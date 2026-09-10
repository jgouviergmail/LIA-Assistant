"""Workboard repository: every read the board makes, and the writes it needs.

Three rules are enforced by SHAPE rather than by discipline:

- **Visibility is ONE predicate**
  (:func:`src.domains.workboard.board_queries.visible_predicate`), reused by
  every read. Two copies would eventually disagree about whose board
  a ticket is on, and the one that drifted would be the one nobody looks at.
- **A page and its counts come from the SAME filtered statement** (ADR-185). A
  column header saying 7 above a column showing 3 is worse than no count at
  all, so the count is an aggregate over the very statement the body reads —
  never the length of a page.
- **Every ordering ends on the primary key.** Without a total order, two
  tickets sharing a sort key can repeat or vanish across a page boundary.

The NULL convention lives here too: ``assignee_user_id IS NULL`` means « the
owner holds it » (see :mod:`src.domains.workboard.models`), so « assigned to
me » must accept both spellings of the same fact.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal
from typing import Any
from uuid import UUID

import structlog
from sqlalchemy import (
    Delete,
    Select,
    Text,
    Update,
    and_,
    case,
    cast,
    delete,
    func,
    or_,
    select,
    update,
)
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.repository import BaseRepository
from src.core.sql_search import LIKE_ESCAPE, escape_like
from src.core.time_utils import now_utc
from src.domains.chat.models import MessageTokenSummary, TokenUsageLog
from src.domains.conversations.models import ConversationMessage
from src.domains.shared.text_normalization import fold_name
from src.domains.workboard.board_queries import (
    BoardFilters,
    apply_assignee,
    needs_me_stmt,
    priority_rank,
    visible_predicate,
)
from src.domains.workboard.constants import (
    CLOSED_STATUSES,
    RUN_ORIGIN_KIND,
    STATUS_ORDER,
    ActorKind,
    AssigneeKind,
    RunError,
    RunOutcome,
    TicketStatus,
)
from src.domains.workboard.models import WorkboardComment, WorkboardTicket, WorkboardTicketEvent

logger = structlog.get_logger(__name__)


@dataclass(frozen=True)
class RunUsage:
    """What one run of a ticket spent.

    Attributes:
        tokens_in: Prompt tokens.
        tokens_out: Completion tokens.
        tokens_cache: Cached prompt tokens — read, and billed at a discount.
        google_requests: Google API calls the turn made.
        cost_eur: What the run cost, in euros — a ``Decimal``, like the column
            it is read from and the column it feeds. A float here mixes with
            neither: the addition onto the ticket's total is evaluated against
            the loaded row, where the attribute is a Decimal, and raises.
    """

    tokens_in: int
    tokens_out: int
    tokens_cache: int
    google_requests: int
    cost_eur: Decimal


class KeepPendingAction:
    """Sentinel type: a settle that leaves ``pending_action`` as it is."""


#: The sentinel a settle passes to leave ``pending_action`` untouched.
KEEP_PENDING_ACTION = KeepPendingAction()


class WorkboardRepository(BaseRepository[WorkboardTicket]):
    """Reads and writes of tickets, comments and events."""

    def __init__(self, db: AsyncSession) -> None:
        super().__init__(db, WorkboardTicket)

    # ------------------------------------------------------------------ reads

    def filtered_stmt(self, user_id: UUID, filters: BoardFilters) -> Select[tuple[WorkboardTicket]]:
        """The visible set, narrowed by everything the reader asked for.

        Public: the board summary (``summary_queries``) counts over it, so
        its figures and the page can never disagree about whose board a
        ticket is on.

        Args:
            user_id: Whose board.
            filters: What the reader asked for.

        Returns:
            The unordered, unpaged statement both the page and its counts use.
        """
        stmt = select(WorkboardTicket).where(visible_predicate(user_id))
        if filters.statuses:
            stmt = stmt.where(WorkboardTicket.status.in_(filters.statuses))
        stmt = apply_assignee(stmt, user_id, filters.assignee)
        if filters.priorities:
            stmt = stmt.where(WorkboardTicket.priority.in_(filters.priorities))
        if filters.overdue:
            stmt = stmt.where(
                WorkboardTicket.due_at < now_utc(),
                WorkboardTicket.status.not_in(tuple(sorted(CLOSED_STATUSES))),
            )
        if filters.due_before is not None:
            stmt = stmt.where(WorkboardTicket.due_at <= filters.due_before)
        if filters.query:
            # A TERM, never a pattern: `%` and `_` are ordinary characters to
            # whoever typed them. Measured on a real server, unescaped, `_`
            # matched every title on the board (the conversation search has
            # escaped them since it was written — one helper for both).
            needle = escape_like(filters.query)
            stmt = stmt.where(WorkboardTicket.title.ilike(f"%{needle}%", escape=LIKE_ESCAPE))
        if filters.include_closed_before is not None:
            # A CLOSED ticket is hidden once it has been closed a while; an
            # OPEN one is never hidden by this filter, however old it is.
            stmt = stmt.where(
                or_(
                    WorkboardTicket.status.not_in(tuple(sorted(CLOSED_STATUSES))),
                    WorkboardTicket.status_changed_at >= filters.include_closed_before,
                )
            )
        return stmt

    def _board_stmt(self, user_id: UUID, filters: BoardFilters) -> Select[tuple[WorkboardTicket]]:
        """The page statement: the filtered set in the reader's order.

        Args:
            user_id: Whose board.
            filters: What the reader asked for, ordering included.

        Returns:
            The ordered statement, still unpaged.
        """
        rank = priority_rank()
        orders: dict[str, tuple[Any, ...]] = {
            "priority": (rank, WorkboardTicket.due_at.asc().nulls_last()),
            "due": (WorkboardTicket.due_at.asc().nulls_last(), rank),
            "updated": (WorkboardTicket.updated_at.desc(),),
            "created": (WorkboardTicket.created_at.desc(),),
        }
        order = orders.get(filters.sort, (WorkboardTicket.position.asc(), rank))
        # The primary key closes every ordering: without a total order, two
        # tickets sharing a sort key repeat or vanish across a page boundary.
        return self.filtered_stmt(user_id, filters).order_by(*order, WorkboardTicket.id.asc())

    def _counts_stmt(self, user_id: UUID, filters: BoardFilters) -> Select[tuple[str, int]]:
        """One exact count per column, over the page's own filter.

        Args:
            user_id: Whose board.
            filters: The SAME filters the page uses.

        Returns:
            The grouped aggregate.
        """
        return (
            self.filtered_stmt(user_id, filters)
            .order_by(None)
            .with_only_columns(WorkboardTicket.status, func.count())
            .group_by(WorkboardTicket.status)
        )

    async def list_board(
        self, user_id: UUID, filters: BoardFilters, *, limit: int, offset: int
    ) -> tuple[list[WorkboardTicket], int]:
        """One page of the board and the EXACT total behind it.

        Args:
            user_id: Whose board.
            filters: What the reader asked for.
            limit: Page size.
            offset: Page offset.

        Returns:
            The rows, and the count over the same filter.
        """
        stmt = self._board_stmt(user_id, filters)
        rows = (await self.db.execute(stmt.limit(limit).offset(offset))).scalars().all()
        total_stmt = select(func.count()).select_from(
            self.filtered_stmt(user_id, filters).order_by(None).subquery()
        )
        total = int((await self.db.execute(total_stmt)).scalar() or 0)
        return list(rows), total

    async def counts_by_status(self, user_id: UUID, filters: BoardFilters) -> dict[str, int]:
        """Exact count per column, every column present.

        A missing key would read as « there is no such column » rather than
        « nothing is in it », and the header would render blank.

        Args:
            user_id: Whose board.
            filters: The page's filters.

        Returns:
            One entry per declared status, zero-filled.
        """
        rows = (await self.db.execute(self._counts_stmt(user_id, filters))).all()
        counts = dict.fromkeys(STATUS_ORDER, 0)
        for status, count in rows:
            counts[str(status)] = int(count)
        return counts

    async def get_visible(self, ticket_id: UUID, user_id: UUID) -> WorkboardTicket | None:
        """The ticket, if it is on this user's board.

        Args:
            ticket_id: The ticket.
            user_id: The reader.

        Returns:
            The row, or None — which the service turns into a neutral 404 so a
            stranger cannot probe whether an id exists.
        """
        stmt = select(WorkboardTicket).where(
            WorkboardTicket.id == ticket_id, visible_predicate(user_id)
        )
        return (await self.db.execute(stmt)).scalar_one_or_none()

    async def count_owned(self, user_id: UUID) -> int:
        """How many tickets this account owns.

        Args:
            user_id: The owner.

        Returns:
            The exact count.
        """
        stmt = (
            select(func.count())
            .select_from(WorkboardTicket)
            .where(WorkboardTicket.owner_user_id == user_id)
        )
        return int((await self.db.execute(stmt)).scalar() or 0)

    async def count_children(self, ticket_id: UUID) -> int:
        """How many sub-tickets a ticket carries.

        Args:
            ticket_id: The parent.

        Returns:
            The exact count.
        """
        stmt = (
            select(func.count())
            .select_from(WorkboardTicket)
            .where(WorkboardTicket.parent_id == ticket_id)
        )
        return int((await self.db.execute(stmt)).scalar() or 0)

    async def list_children(self, ticket_id: UUID) -> list[WorkboardTicket]:
        """The sub-tickets of a ticket, in board order.

        Args:
            ticket_id: The parent.

        Returns:
            The children.
        """
        stmt = (
            select(WorkboardTicket)
            .where(WorkboardTicket.parent_id == ticket_id)
            .order_by(WorkboardTicket.position.asc(), WorkboardTicket.id.asc())
        )
        return list((await self.db.execute(stmt)).scalars().all())

    async def list_comments(self, ticket_id: UUID) -> list[WorkboardComment]:
        """The comment thread of a ticket, oldest first.

        Args:
            ticket_id: The ticket.

        Returns:
            The comments.
        """
        stmt = (
            select(WorkboardComment)
            .where(WorkboardComment.ticket_id == ticket_id)
            .order_by(WorkboardComment.created_at.asc(), WorkboardComment.id.asc())
        )
        return list((await self.db.execute(stmt)).scalars().all())

    async def owner_notes_since(
        self, ticket_id: UUID, owner_user_id: UUID, *, since: datetime | None, limit: int
    ) -> list[WorkboardComment]:
        """The owner's own comments since an instant, latest ``limit`` of them.

        The OWNER's, by shape: the author is a parameter and the kind is pinned
        to ``user``, so a peer's words — a stranger's, from the brief's point of
        view — can never come back from this query however it is called
        (ADR-167/170, the brief's rule).

        Args:
            ticket_id: The ticket.
            owner_user_id: The owner, who is the only author accepted.
            since: Only comments written after this instant; None takes them
                all — a ticket LIA never ran has no « last run ».
            limit: How many at most, the most recent kept.

        Returns:
            The comments, oldest first.
        """
        stmt = select(WorkboardComment).where(
            WorkboardComment.ticket_id == ticket_id,
            WorkboardComment.author_user_id == owner_user_id,
            WorkboardComment.author_kind == ActorKind.USER.value,
        )
        if since is not None:
            stmt = stmt.where(WorkboardComment.created_at > since)
        stmt = stmt.order_by(WorkboardComment.created_at.desc(), WorkboardComment.id.desc()).limit(
            limit
        )
        latest = list((await self.db.execute(stmt)).scalars().all())
        latest.reverse()
        return latest

    async def list_events(self, ticket_id: UUID) -> list[WorkboardTicketEvent]:
        """The history of a ticket, oldest first.

        Args:
            ticket_id: The ticket.

        Returns:
            The events.
        """
        stmt = (
            select(WorkboardTicketEvent)
            .where(WorkboardTicketEvent.ticket_id == ticket_id)
            .order_by(WorkboardTicketEvent.created_at.asc(), WorkboardTicketEvent.id.asc())
        )
        return list((await self.db.execute(stmt)).scalars().all())

    async def find_by_title(self, user_id: UUID, title: str) -> list[WorkboardTicket]:
        """Visible tickets whose FOLDED title equals the folded needle.

        ``fold_name`` is the ONE authority on identity: re-expressing it in SQL
        would make the database a second one, and the two diverge on ligatures
        and on ``ß`` (ADR-185).

        The read is therefore in two steps rather than one narrowed query. A
        ``ILIKE`` pre-filter on the raw needle looks like a harmless
        optimisation and is not: it is STRICTER than the folding it feeds, so
        it discards exactly the rows folding exists to catch — measured
        2026-09-09, « reserver la salle » found nothing while the board held
        « Réserver la salle ». **A narrowing filter must be more permissive
        than the decider, never less.** Step one reads two light columns over a
        set the account cap already bounds; step two loads only what folding
        chose.

        Args:
            user_id: The reader.
            title: What they called the ticket.

        Returns:
            Every match — one is a resolution, several are an ambiguity the
            service refuses rather than guessing at.
        """
        needle = fold_name(title)
        if not needle:
            return []
        rows = (
            await self.db.execute(
                select(WorkboardTicket.id, WorkboardTicket.title).where(visible_predicate(user_id))
            )
        ).all()
        matched = [row.id for row in rows if fold_name(row.title) == needle]
        if not matched:
            return []
        found = (
            await self.db.execute(
                select(WorkboardTicket)
                .where(WorkboardTicket.id.in_(matched))
                .order_by(WorkboardTicket.created_at.asc(), WorkboardTicket.id.asc())
            )
        ).scalars()
        return list(found)

    async def needs_me(
        self, user_id: UUID, now: datetime, *, limit: int = 20, offset: int = 0
    ) -> tuple[list[WorkboardTicket], int]:
        """Tickets waiting on this account, plus the late ones on its board.

        Args:
            user_id: The reader.
            now: The instant lateness is judged against.
            limit: Page size.
            offset: Page offset.

        Returns:
            The page and the EXACT total behind it.
        """
        ids = needs_me_stmt(user_id, now).subquery()
        stmt = (
            select(WorkboardTicket)
            .where(WorkboardTicket.id.in_(select(ids.c.id)))
            .order_by(WorkboardTicket.due_at.asc().nulls_last(), WorkboardTicket.id.asc())
        )
        rows = (await self.db.execute(stmt.limit(limit).offset(offset))).scalars().all()
        total = int((await self.db.execute(select(func.count()).select_from(ids))).scalar() or 0)
        return list(rows), total

    async def count_needs_me(self, user_id: UUID, now: datetime) -> int:
        """How many tickets wait on this account — the aggregate alone.

        The hub badge needs the TOTAL and nothing else, and it is read on every
        dashboard load: asking :meth:`needs_me` for it costs a second statement
        and a row nobody looks at. Same predicate, so the badge and the section
        can never disagree about what « needs me » means.

        Args:
            user_id: The reader.
            now: The instant lateness is judged against.

        Returns:
            The exact count.
        """
        stmt = select(func.count()).select_from(needs_me_stmt(user_id, now).subquery())
        return int((await self.db.execute(stmt)).scalar() or 0)

    async def list_held_between(self, owner_id: UUID, assignee_id: UUID) -> list[WorkboardTicket]:
        """Tickets one account owns and another holds.

        The pair IS the connection: ``peer_connections`` carries one row per
        pair for life, so a removed connection is found by its two
        participants without the ticket storing a connection id (ADR-276).

        Args:
            owner_id: The board's owner.
            assignee_id: The account holding the tickets.

        Returns:
            The tickets to release.
        """
        stmt = select(WorkboardTicket).where(
            WorkboardTicket.owner_user_id == owner_id,
            WorkboardTicket.assignee_user_id == assignee_id,
        )
        return list((await self.db.execute(stmt)).scalars().all())

    async def list_nudge_worthy(
        self,
        user_id: UUID,
        *,
        due_before: datetime,
        waiting_since: datetime,
        cooldown_before: datetime,
        limit: int,
    ) -> list[WorkboardTicket]:
        """Tickets on this board worth interrupting the person about (D14).

        Everything narrows in SQL rather than in Python: a board may hold
        thousands of tickets and the heartbeat wants at most a handful, so
        reading them all to keep eight would make the cap a formality.

        Two families of reason qualify a ticket, and a row matching either is
        returned once:

        - it is **overdue** or **due soon** (``due_at`` at or before
          ``due_before``) — and a PERSON holds it, because a deadline on a
          ticket LIA holds is LIA's backlog, not the person's;
        - it is **stopped on the person** (``waiting`` for an answer, or
          ``validating`` a result) since at or before ``waiting_since``,
          whoever holds it.

        Closed tickets never qualify, and neither does ``idea``: a note nobody
        has committed to is not late.

        Args:
            user_id: Whose board.
            due_before: The far edge of the due window (now + the setting).
            waiting_since: A ``waiting`` ticket older than this qualifies.
            cooldown_before: A ticket nudged after this instant is still
                cooling down.
            limit: How many rows at most.

        Returns:
            The tickets to offer, most pressing first.
        """
        stmt = (
            select(WorkboardTicket)
            .where(
                visible_predicate(user_id),
                WorkboardTicket.status.notin_([*CLOSED_STATUSES, TicketStatus.IDEA.value]),
                or_(
                    WorkboardTicket.last_nudged_at.is_(None),
                    WorkboardTicket.last_nudged_at <= cooldown_before,
                ),
                or_(
                    # A deadline is the PERSON's to keep only while they hold
                    # the ticket: one LIA holds is LIA's own backlog, and
                    # nagging the person about it would be noise.
                    and_(
                        WorkboardTicket.assignee_kind == AssigneeKind.HUMAN.value,
                        WorkboardTicket.due_at.is_not(None),
                        WorkboardTicket.due_at <= due_before,
                    ),
                    # Stopped on the person, whoever holds it: a question LIA
                    # asked, or a result awaiting validation.
                    and_(
                        WorkboardTicket.status.in_(
                            [
                                TicketStatus.WAITING.value,
                                TicketStatus.CONFIRMING.value,
                                TicketStatus.VALIDATING.value,
                            ]
                        ),
                        WorkboardTicket.status_changed_at <= waiting_since,
                    ),
                ),
            )
            # An ORDER BY is not decoration under a LIMIT: without it
            # PostgreSQL is free to return any rows at all, and the cap would
            # silently keep the least pressing ones (ADR-273).
            .order_by(
                priority_rank(),
                WorkboardTicket.due_at.asc().nulls_last(),
                WorkboardTicket.id.asc(),
            )
            .limit(limit)
        )
        return list((await self.db.execute(stmt)).scalars().all())

    async def latest_lia_comments(self, ticket_ids: list[UUID]) -> dict[UUID, str]:
        """What LIA last wrote on each of these tickets.

        A ``waiting`` ticket carries its question in the run's own comment and
        a ``validating`` one carries what was delivered — the one thing a nudge
        must be able to quote rather than paraphrase. One query for the whole
        set, newest first, so the first row seen per ticket is the latest.

        Args:
            ticket_ids: The tickets to read.

        Returns:
            Ticket id -> the body of LIA's latest comment; absent when LIA
            never wrote on it.
        """
        if not ticket_ids:
            return {}
        stmt = (
            select(WorkboardComment)
            .where(
                WorkboardComment.ticket_id.in_(ticket_ids),
                WorkboardComment.author_kind == ActorKind.LIA.value,
            )
            .order_by(
                WorkboardComment.ticket_id,
                WorkboardComment.created_at.desc(),
                WorkboardComment.id.desc(),
            )
        )
        latest: dict[UUID, str] = {}
        for comment in (await self.db.execute(stmt)).scalars().all():
            latest.setdefault(comment.ticket_id, comment.body)
        return latest

    async def bump_nudged(self, ticket_ids: list[UUID], *, user_id: UUID) -> int:
        """Start the cooldown on the tickets a delivered notification named.

        The count is incremented server-side rather than read and rewritten in
        Python: two ticks racing would otherwise lose one of the increments.

        ``user_id`` is not decoration — it is the clause that stops an id
        arriving from anywhere else from touching somebody else's ticket.

        Args:
            ticket_ids: The tickets the notification surfaced.
            user_id: Whose board they must be on.

        Returns:
            How many rows were stamped.
        """
        if not ticket_ids:
            return 0
        stmt = (
            update(WorkboardTicket)
            .where(
                WorkboardTicket.id.in_(ticket_ids),
                visible_predicate(user_id),
            )
            .values(
                last_nudged_at=now_utc(),
                nudge_count=WorkboardTicket.nudge_count + 1,
            )
        )
        return await self._rows_affected(stmt)

    # ------------------------------------------------------ the run lifecycle

    async def _rows_affected(self, stmt: Update | Delete) -> int:
        """Execute one DML statement and say how many rows it touched.

        ``AsyncSession.execute`` is typed as returning a ``Result``, which
        carries no ``rowcount``; an UPDATE or a DELETE actually returns a
        ``CursorResult``, which does. The narrowing lives here once rather than
        at every write — five conditional writes hang off it, and five copies
        of the same ignore is how one of them ends up not being checked at all.

        Args:
            stmt: The UPDATE or DELETE to run.

        Returns:
            Rows the statement matched.
        """
        result = await self.db.execute(stmt)
        return int(result.rowcount or 0)  # type: ignore[attr-defined]

    def claimable_stmt(
        self, now: datetime, *, max_runs: int, max_attempts: int
    ) -> Select[tuple[WorkboardTicket]]:
        """The next ticket the sweep may take, locked against other workers.

        ``FOR UPDATE SKIP LOCKED`` is what makes two workers safe: whoever
        holds the row runs it and the other steps over it rather than queueing
        behind it. ONE ticket at a time on purpose — a worker that claimed five
        and was killed would strand five.

        Only ``todo`` is eligible: ``idea`` is a thought somebody noted, and
        running it would turn « I might » into « I did ».

        Args:
            now: The instant readiness is judged against.
            max_runs: Runs a ticket may have in its whole life — the bound on
                the hidden transcripts it accumulates.
            max_attempts: Attempts ONE run may make before the ticket stops
                being offered.

        Returns:
            The locking statement.
        """
        return (
            select(WorkboardTicket)
            .where(
                WorkboardTicket.assignee_kind == AssigneeKind.LIA.value,
                WorkboardTicket.status == TicketStatus.TODO.value,
                WorkboardTicket.run_claimed_at.is_(None),
                WorkboardTicket.run_count < max_runs,
                WorkboardTicket.run_attempts < max_attempts,
                or_(WorkboardTicket.start_at.is_(None), WorkboardTicket.start_at <= now),
                or_(
                    WorkboardTicket.run_not_before.is_(None),
                    WorkboardTicket.run_not_before <= now,
                ),
            )
            # Ready longest goes first, and a ticket with no start date has
            # been ready since it was written. The primary key closes the
            # order, as every ordering here does.
            .order_by(
                WorkboardTicket.start_at.asc().nulls_first(),
                WorkboardTicket.created_at.asc(),
                WorkboardTicket.id.asc(),
            )
            .limit(1)
            .with_for_update(skip_locked=True)
        )

    async def claim_ticket(
        self, ticket: WorkboardTicket, *, run_id: str, now: datetime
    ) -> WorkboardTicket | None:
        """Take a ticket for a run, in ONE conditional statement.

        The eligibility is re-checked inside the UPDATE: between the scan and
        the write another worker may have taken the row, or the person may have
        moved it. A claim followed by work decided outside the claiming
        statement is the forbidden shape.

        Args:
            ticket: The row the scan returned.
            run_id: The run about to start — the registers' join key.
            now: The claim instant.

        Returns:
            The claimed row, or None when somebody got there first.
        """
        stmt = (
            update(WorkboardTicket)
            .where(
                WorkboardTicket.id == ticket.id,
                WorkboardTicket.status == TicketStatus.TODO.value,
                WorkboardTicket.run_claimed_at.is_(None),
            )
            .values(
                status=TicketStatus.IN_PROGRESS.value,
                status_changed_at=now,
                run_claimed_at=now,
                run_attempts=WorkboardTicket.run_attempts + 1,
                run_count=WorkboardTicket.run_count + 1,
                last_run_id=run_id,
            )
            .returning(WorkboardTicket)
        )
        return (await self.db.execute(stmt)).scalar_one_or_none()

    async def settle_run(
        self,
        *,
        ticket_id: UUID,
        run_id: str,
        status: str,
        outcome: str,
        now: datetime,
        error: str | None = None,
        usage: RunUsage | None = None,
        hand_back: bool = False,
        pending_action: dict[str, Any] | None | KeepPendingAction = KEEP_PENDING_ACTION,
    ) -> bool:
        """Close a run on the ticket it belongs to.

        Conditional on ``last_run_id``: a person who moved the ticket while the
        run was in flight WINS, and the late settle matches nothing rather than
        dragging the ticket back to a column they left.

        ``run_attempts`` is cleared here: it bounds ONE run, never the ticket's
        lifetime — the lifetime is what ``run_count`` bounds, and that one is
        never given back by a run that actually ran.

        Args:
            ticket_id: The ticket.
            run_id: The run settling; a stale one matches nothing.
            status: The column the ticket lands in.
            outcome: A :class:`RunOutcome` value.
            now: The settle instant.
            error: A typed code and a bounded message, on failure.
            usage: What the run spent. Stored twice on purpose: as the LAST
                run's figures, which the panel names, and ADDED to the
                ticket's running total, which answers « what has this cost
                me ». The addition is column arithmetic inside the UPDATE —
                a SELECT-then-add would lose a concurrent settle.
            hand_back: Give the ticket back to its owner in the same statement.
                A run that stops on a QUESTION or delivers a result to check
                has passed the ball: leaving it assigned to LIA would show the
                person a ticket LIA holds while nothing is going to happen
                until they answer.
            pending_action: The draft the person must confirm on the ticket
                (lot 7): a dict to store one, None to clear the previous one —
                an approval is spent by the run that replayed it — or the
                sentinel to leave the column alone, which is what a FAILED run
                does so a retry can still replay what was approved.

        Returns:
            True when the settle landed; False when the run lost the row.
        """
        stmt = (
            update(WorkboardTicket)
            .where(
                WorkboardTicket.id == ticket_id,
                WorkboardTicket.last_run_id == run_id,
                WorkboardTicket.status == TicketStatus.IN_PROGRESS.value,
            )
            .values(
                status=status,
                status_changed_at=now,
                run_claimed_at=None,
                run_attempts=0,
                last_run_at=now,
                last_run_outcome=outcome,
                last_run_error=error,
                last_run_tokens_in=None if usage is None else usage.tokens_in,
                last_run_tokens_out=None if usage is None else usage.tokens_out,
                last_run_cost_eur=None if usage is None else usage.cost_eur,
                **(
                    {}
                    if usage is None
                    else {
                        "total_tokens_in": WorkboardTicket.total_tokens_in + usage.tokens_in,
                        "total_tokens_out": WorkboardTicket.total_tokens_out + usage.tokens_out,
                        "total_tokens_cache": (
                            WorkboardTicket.total_tokens_cache + usage.tokens_cache
                        ),
                        "total_google_requests": (
                            WorkboardTicket.total_google_requests + usage.google_requests
                        ),
                        "total_cost_eur": WorkboardTicket.total_cost_eur + usage.cost_eur,
                    }
                ),
                # NULL is « the owner holds it » (ADR-276), so one assignment
                # covers both columns of the convention.
                **(
                    {
                        "assignee_kind": AssigneeKind.HUMAN.value,
                        "assignee_user_id": None,
                        "follow_assignee": False,
                    }
                    if hand_back
                    else {}
                ),
                **(
                    {}
                    if isinstance(pending_action, KeepPendingAction)
                    else {"pending_action": pending_action}
                ),
            )
        )
        return bool(await self._rows_affected(stmt))

    async def release_claim(
        self,
        *,
        ticket_id: UUID,
        run_id: str,
        outcome: str,
        now: datetime,
        retry_after: datetime | None = None,
    ) -> bool:
        """Hand a ticket back without having run it.

        A quota refusal and a busy thread are NOT failures (ADR-272's logging
        rule): nothing ran, so the ticket returns to ``todo`` AND the run it
        never made is given back to its lifetime budget — otherwise a fortnight
        of quota refusals would silently exhaust a ticket's runs.

        Args:
            ticket_id: The ticket.
            run_id: The run releasing it; a stale one matches nothing.
            outcome: ``skipped_quota`` or ``skipped_busy``.
            now: The release instant.
            retry_after: Do not offer it again before this instant.

        Returns:
            True when the release landed.
        """
        stmt = (
            update(WorkboardTicket)
            .where(
                WorkboardTicket.id == ticket_id,
                WorkboardTicket.last_run_id == run_id,
                WorkboardTicket.status == TicketStatus.IN_PROGRESS.value,
            )
            .values(
                status=TicketStatus.TODO.value,
                status_changed_at=now,
                run_claimed_at=None,
                run_attempts=0,
                run_count=WorkboardTicket.run_count - 1,
                run_not_before=retry_after,
                last_run_at=now,
                last_run_outcome=outcome,
            )
        )
        return bool(await self._rows_affected(stmt))

    async def reap_stale_claims(self, *, older_than: datetime) -> int:
        """Give back the tickets a dead worker still holds.

        Released, never settled: nobody knows how that run ended, and a settle
        would state an outcome nobody observed. The attempt it already counted
        is what stops an unrunnable ticket from being retried for ever — which
        is why this does NOT reset ``run_attempts``.

        Args:
            older_than: Claims older than this instant are stranded.

        Returns:
            How many tickets were released.
        """
        stmt = (
            update(WorkboardTicket)
            .where(
                WorkboardTicket.status == TicketStatus.IN_PROGRESS.value,
                WorkboardTicket.run_claimed_at.is_not(None),
                WorkboardTicket.run_claimed_at < older_than,
            )
            .values(
                status=TicketStatus.TODO.value,
                status_changed_at=older_than,
                run_claimed_at=None,
                last_run_outcome=RunOutcome.FAILED.value,
                last_run_error=RunError.RUN_REAPED.value,
            )
        )
        return await self._rows_affected(stmt)

    async def run_usage(self, run_id: str) -> RunUsage:
        """What one run spent, in the vocabulary the chat already shows.

        Read from ``message_token_summary``, the ONE row a turn files under its
        run id — the very record the chat's own totals are built from, so a
        ticket and a conversation can never state the same run differently. The
        per-node ``token_usage_logs`` rows are the FALLBACK, not a second
        authority: they are what the summary is itself built from, and a run
        that broke before the summary was written still has them.

        Snapshotted onto the ticket rather than joined at render time:
        ``token_usage_logs`` is BILLING_RETAINED and outlives the account
        (ADR-263), so a board reading it live would show a price for a run
        whose whole conversation had been erased.

        Args:
            run_id: The run, shared with the three registers.

        Returns:
            The five figures; zeros when the run called no model — a ticket
            answered from context alone still gets a settled price rather than
            an empty one.
        """
        summary = (
            await self.db.execute(
                select(
                    MessageTokenSummary.total_prompt_tokens,
                    MessageTokenSummary.total_completion_tokens,
                    MessageTokenSummary.total_cached_tokens,
                    MessageTokenSummary.google_api_requests,
                    MessageTokenSummary.total_cost_eur,
                ).where(MessageTokenSummary.run_id == run_id)
            )
        ).first()
        if summary is not None:
            tokens_in, tokens_out, cache, google, cost = summary
            return RunUsage(
                tokens_in=int(tokens_in or 0),
                tokens_out=int(tokens_out or 0),
                tokens_cache=int(cache or 0),
                google_requests=int(google or 0),
                cost_eur=Decimal(cost or 0),
            )
        node_rows = (
            await self.db.execute(
                select(
                    func.sum(TokenUsageLog.prompt_tokens),
                    func.sum(TokenUsageLog.completion_tokens),
                    func.sum(TokenUsageLog.cached_tokens),
                    func.sum(TokenUsageLog.cost_eur),
                ).where(TokenUsageLog.run_id == run_id)
            )
        ).one()
        prompt, completion, cache, cost = node_rows
        return RunUsage(
            tokens_in=int(prompt or 0),
            tokens_out=int(completion or 0),
            tokens_cache=int(cache or 0),
            google_requests=0,
            cost_eur=Decimal(cost or 0),
        )

    async def hidden_volume(self) -> tuple[int, int]:
        """What the hidden transcripts cost right now.

        The owner accepted archiving a run's rows rather than dropping them on
        ONE condition: that the growth be watched rather than assumed (D3b).
        This is that measurement, and it is EXACT rather than estimated — the
        set is small by construction (two rows per run, ten runs per ticket at
        most, ninety days of retention), and the partial index makes counting
        it cheaper than estimating it would be.

        ``pg_column_size`` covers the two columns that actually carry weight:
        a run's brief and its answer, and the stamp beside them.

        Returns:
            ``(rows, bytes)``.
        """
        stmt = select(
            func.count(),
            func.coalesce(
                func.sum(
                    func.pg_column_size(ConversationMessage.content)
                    + func.pg_column_size(ConversationMessage.message_metadata)
                ),
                0,
            ),
        ).where(ConversationMessage.hidden.is_(True))
        rows, size = (await self.db.execute(stmt)).one()
        return int(rows or 0), int(size or 0)

    async def purge_hidden_rows(self, *, closed_before: datetime) -> int:
        """Remove the hidden transcripts of tickets closed long enough ago.

        This is one half of what makes hidden rows acceptable at all — the
        other half is the per-ticket run cap. What goes is the verbatim of a
        run nobody reads any more; what stays is the ticket's COMMENT, which
        holds the answer, and the register rows, which keep their dated
        tombstones (ADR-263).

        The ticket id is matched as TEXT: it is a JSON value written by the
        stamp, and casting it to ``uuid`` would make one malformed row fail the
        whole sweep.

        Args:
            closed_before: Tickets closed before this instant are past
                retention.

        Returns:
            How many rows were removed.
        """
        closed_tickets = select(cast(WorkboardTicket.id, Text)).where(
            WorkboardTicket.status.in_(tuple(sorted(CLOSED_STATUSES))),
            WorkboardTicket.status_changed_at < closed_before,
        )
        living_tickets = select(cast(WorkboardTicket.id, Text))
        stamped = ConversationMessage.message_metadata[(RUN_ORIGIN_KIND, "ticket_id")].astext
        stmt = delete(ConversationMessage).where(
            ConversationMessage.hidden.is_(True),
            or_(
                stamped.in_(closed_tickets),
                # A ticket DELETED while its rows stood: nothing joins them any
                # more, so the only bound left is age — the same window,
                # counted from the row itself. Without this branch the rows of
                # every deleted ticket stayed for ever, and nothing said so.
                and_(
                    stamped.is_not(None),
                    stamped.not_in(living_tickets),
                    ConversationMessage.created_at < closed_before,
                ),
            ),
        )
        return await self._rows_affected(stmt)

    # ----------------------------------------------------------------- writes

    async def next_position(self, owner_id: UUID, status: str) -> int:
        """The position a new ticket takes at the end of a column.

        Args:
            owner_id: Whose board.
            status: The column.

        Returns:
            One past the last position, or 0 for an empty column.
        """
        stmt = select(func.coalesce(func.max(WorkboardTicket.position), -1) + 1).where(
            WorkboardTicket.owner_user_id == owner_id, WorkboardTicket.status == status
        )
        return int((await self.db.execute(stmt)).scalar() or 0)

    async def list_column_ids(self, owner_id: UUID, status: str) -> list[UUID]:
        """Every ticket of one column, in its current order.

        Args:
            owner_id: Whose board.
            status: The column.

        Returns:
            The ids, in board order.
        """
        stmt = (
            select(WorkboardTicket.id)
            .where(WorkboardTicket.owner_user_id == owner_id, WorkboardTicket.status == status)
            .order_by(WorkboardTicket.position.asc(), WorkboardTicket.id.asc())
        )
        return list((await self.db.execute(stmt)).scalars().all())

    async def renumber_column(self, owner_id: UUID, status: str, ordered_ids: list[UUID]) -> int:
        """Write the order of one column in ONE statement.

        A row-by-row update would be N round trips and a window in which the
        column carries two tickets at the same position.

        Args:
            owner_id: Whose board.
            status: The column.
            ordered_ids: Every ticket of the column, in its new order.

        Returns:
            Rows updated.
        """
        if not ordered_ids:
            return 0
        mapping = {ticket_id: index for index, ticket_id in enumerate(ordered_ids)}
        stmt = (
            update(WorkboardTicket)
            .where(
                WorkboardTicket.owner_user_id == owner_id,
                WorkboardTicket.status == status,
                WorkboardTicket.id.in_(ordered_ids),
            )
            .values(
                position=case(mapping, value=WorkboardTicket.id, else_=WorkboardTicket.position)
            )
        )
        return await self._rows_affected(stmt)

    async def add_comment(
        self,
        *,
        ticket_id: UUID,
        author_kind: str,
        author_user_id: UUID | None,
        body: str,
        run_id: str | None = None,
    ) -> WorkboardComment:
        """Append one comment to a ticket.

        Args:
            ticket_id: The ticket.
            author_kind: ``user`` | ``lia`` | ``peer``.
            author_user_id: The account, or None when LIA wrote it.
            body: Plain text.
            run_id: The run that wrote it, when LIA did.

        Returns:
            The flushed row (the caller owns the commit).
        """
        comment = WorkboardComment(
            ticket_id=ticket_id,
            author_kind=author_kind,
            author_user_id=author_user_id,
            body=body,
            run_id=run_id,
        )
        self.db.add(comment)
        await self.db.flush()
        return comment

    async def add_event(
        self,
        *,
        ticket_id: UUID,
        actor_kind: str,
        actor_user_id: UUID | None,
        kind: str,
        payload: dict[str, object] | None = None,
    ) -> WorkboardTicketEvent:
        """Append one event to a ticket's history.

        Args:
            ticket_id: The ticket.
            actor_kind: ``user`` | ``lia`` | ``peer``.
            actor_user_id: The account, or None when LIA acted.
            kind: A :class:`TicketEventKind` value.
            payload: Bounded ``{from, to}`` facts; never free text.

        Returns:
            The flushed row (the caller owns the commit).
        """
        event = WorkboardTicketEvent(
            ticket_id=ticket_id,
            actor_kind=actor_kind,
            actor_user_id=actor_user_id,
            kind=kind,
            payload=payload,
        )
        self.db.add(event)
        await self.db.flush()
        return event
