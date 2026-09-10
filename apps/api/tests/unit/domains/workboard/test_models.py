"""The vocabulary is ONE tuple, and the tables say what they mean (ADR-276).

Three classes of assertion, each closing a defect the repository has already
paid for elsewhere:

- **the vocabulary** — column order derived from the enum, never a second list
  a frontend or a migration could reorder (the ``DOMAIN_REGISTRY`` rule);
- **the shape** — the FK actions and the CHECK constraint that make a dangling
  assignee unrepresentable BY CONSTRUCTION, on every path that can remove an
  account, rather than by a release step four call sites must remember;
- **the append-only event log** — a ledger row is never updated, so it carries
  no ``updated_at`` (the ``peer_access_log`` precedent).
"""

from __future__ import annotations

import uuid

import pytest

from src.domains.workboard.constants import (
    CLOSED_STATUSES,
    STATUS_ORDER,
    ActorKind,
    AssigneeKind,
    RunOutcome,
    TicketEventKind,
    TicketPriority,
    TicketStatus,
)
from src.domains.workboard.models import WorkboardComment, WorkboardTicket, WorkboardTicketEvent

pytestmark = pytest.mark.unit


class TestVocabulary:
    """One declaration; every reader derives from it."""

    def test_column_order_is_the_enum_order(self) -> None:
        assert STATUS_ORDER == tuple(s.value for s in TicketStatus)
        assert STATUS_ORDER == (
            "idea",
            "todo",
            "in_progress",
            "waiting",
            # Lot 7: drawn only while it holds a ticket, but a column all the
            # same — the enum is the ONE declaration every reader derives from.
            "confirming",
            "validating",
            "done",
        )

    def test_a_ticket_is_closed_by_one_column_only(self) -> None:
        """« Annulé » was dropped (2026-09-09): a board is read ACROSS, and what
        was cancelled is finished — the history's ``reason`` says why."""
        assert CLOSED_STATUSES == frozenset({"done"})
        assert CLOSED_STATUSES <= set(STATUS_ORDER)

    def test_priorities_are_ordered_low_to_urgent(self) -> None:
        assert [p.value for p in TicketPriority] == ["low", "medium", "high", "urgent"]

    def test_assignee_and_actor_kinds(self) -> None:
        assert {k.value for k in AssigneeKind} == {"human", "lia"}
        assert {k.value for k in ActorKind} == {"user", "lia", "peer"}

    def test_event_kinds(self) -> None:
        assert {k.value for k in TicketEventKind} == {
            "created",
            "status_changed",
            "assigned",
            "priority_changed",
            "dates_changed",
            "run_started",
            "run_finished",
            "follow_changed",
        }

    def test_run_outcomes_separate_a_refusal_from_a_failure(self) -> None:
        """A quota refusal is not a generation failure (ADR-272)."""
        assert {o.value for o in RunOutcome} == {
            "success",
            "waiting",
            "confirming",
            "failed",
            "skipped_quota",
            "skipped_busy",
        }

    def test_the_stored_columns_document_the_CURRENT_vocabulary(self) -> None:
        """A column comment is what a DBA reads at the psql prompt, and it was a THIRD
        hand-written copy of the vocabulary: it still listed ``cancelled``,
        dropped at lot 8, and had never learnt ``confirming``, added at lot 7.
        Derived from the enums, so a column added to one cannot leave a stale
        sentence behind — the drift check then asks for the migration that
        writes it, which is exactly the right question."""
        columns = WorkboardTicket.__table__.c
        assert columns.status.comment == " | ".join(STATUS_ORDER)
        assert columns.last_run_outcome.comment == " | ".join(o.value for o in RunOutcome)

    def test_every_vocabulary_value_fits_its_column(self) -> None:
        """A value longer than its column would fail at INSERT, in production."""
        columns = WorkboardTicket.__table__.c
        assert max(len(s.value) for s in TicketStatus) <= columns.status.type.length
        assert max(len(p.value) for p in TicketPriority) <= columns.priority.type.length
        assert max(len(k.value) for k in AssigneeKind) <= columns.assignee_kind.type.length
        assert max(len(a.value) for a in ActorKind) <= columns.created_by.type.length
        assert max(len(o.value) for o in RunOutcome) <= columns.last_run_outcome.type.length
        event_columns = WorkboardTicketEvent.__table__.c
        assert max(len(k.value) for k in TicketEventKind) <= event_columns.kind.type.length


class TestTicketTable:
    """The shape that makes an inconsistent row unrepresentable."""

    def test_table_names(self) -> None:
        assert WorkboardTicket.__tablename__ == "workboard_tickets"
        assert WorkboardComment.__tablename__ == "workboard_comments"
        assert WorkboardTicketEvent.__tablename__ == "workboard_ticket_events"

    def test_defaults(self) -> None:
        columns = WorkboardTicket.__table__.c
        assert columns.status.default.arg == TicketStatus.TODO.value
        assert columns.priority.default.arg == TicketPriority.MEDIUM.value
        assert columns.assignee_kind.default.arg == AssigneeKind.HUMAN.value
        assert columns.created_by.default.arg == ActorKind.USER.value
        assert columns.follow_owner.default.arg is False
        assert columns.follow_assignee.default.arg is False
        assert columns.run_attempts.default.arg == 0
        assert columns.run_count.default.arg == 0
        assert columns.nudge_count.default.arg == 0
        assert columns.position.default.arg == 0

    def test_owner_cascades_and_a_departing_assignee_releases_the_ticket(self) -> None:
        """Four paths hard-delete a ``users`` row and only ONE runs the purge
        (demo purge, unverified cleanup, admin hard delete, GDPR delete).

        - CASCADE on the assignee would destroy the OWNER's ticket when their
          peer leaves — their own work, on their own board.
        - RESTRICT would block the three paths that never release, turning a
          safety net into an outage on an admin operation.
        - SET NULL releases the ticket back to its owner on EVERY path, present
          and future, because NULL means « the owner holds it ».
        """
        columns = WorkboardTicket.__table__.c
        owner_fk = next(iter(columns.owner_user_id.foreign_keys))
        assignee_fk = next(iter(columns.assignee_user_id.foreign_keys))
        assert owner_fk.ondelete == "CASCADE"
        assert assignee_fk.ondelete == "SET NULL"
        assert columns.assignee_user_id.nullable is True

    def test_effective_assignee_reads_null_as_the_owner(self) -> None:
        """One helper, so no reader re-implements the NULL convention."""
        owner_id = uuid.uuid4()
        peer_id = uuid.uuid4()
        own = WorkboardTicket(owner_user_id=owner_id, assignee_user_id=None)
        held = WorkboardTicket(owner_user_id=owner_id, assignee_user_id=peer_id)
        assert own.effective_assignee_id == owner_id
        assert held.effective_assignee_id == peer_id

    def test_parent_cascades(self) -> None:
        parent_fk = next(iter(WorkboardTicket.__table__.c.parent_id.foreign_keys))
        assert parent_fk.ondelete == "CASCADE"

    def test_no_cross_column_check_can_survive_a_cascade(self) -> None:
        """No CHECK spans two columns a foreign-key action can touch.

        Measured 2026-09-09 on a real PostgreSQL server: deleting a peer's account fires
        two independent FK actions on one ticket row, and a CHECK tying those
        columns rejects whichever intermediate state comes first — an order the
        standard does not fix. ``CHECK`` cannot be ``DEFERRABLE`` in
        PostgreSQL, so such an invariant belongs to the service, which
        re-resolves the accepted connection at every write (D8).
        """
        assert "peer_connection_id" not in WorkboardTicket.__table__.c
        assert WorkboardTicket.__table__.constraints == {
            constraint
            for constraint in WorkboardTicket.__table__.constraints
            if constraint.__class__.__name__ != "CheckConstraint"
        }

    def test_the_sweep_scan_has_a_partial_index(self) -> None:
        indexes = {index.name: index for index in WorkboardTicket.__table__.indexes}
        assert "ix_workboard_tickets_lia_todo" in indexes
        where = str(indexes["ix_workboard_tickets_lia_todo"].dialect_options["postgresql"]["where"])
        assert "assignee_kind = 'lia'" in where
        assert "status = 'todo'" in where
        assert "run_claimed_at IS NULL" in where

    def test_board_reads_are_indexed_from_both_sides(self) -> None:
        """A ticket is on U's board as owner OR as assignee — both paths indexed."""
        names = {index.name for index in WorkboardTicket.__table__.indexes}
        assert "ix_workboard_tickets_owner_status" in names
        assert "ix_workboard_tickets_assignee_status" in names

    def test_nullable_contract(self) -> None:
        columns = WorkboardTicket.__table__.c
        for required in (
            "owner_user_id",
            "title",
            "status",
            "priority",
            "assignee_kind",
            "position",
            "created_by",
            "status_changed_at",
        ):
            assert columns[required].nullable is False, required
        for optional in (
            "parent_id",
            "description",
            "start_at",
            "due_at",
            "assignee_user_id",
            "pending_action",
        ):
            assert columns[optional].nullable is True, optional


class TestChildTables:
    """Comments and events die with their ticket; the log is append-only."""

    def test_children_cascade_from_the_ticket(self) -> None:
        for model in (WorkboardComment, WorkboardTicketEvent):
            fk = next(iter(model.__table__.c.ticket_id.foreign_keys))
            assert fk.ondelete == "CASCADE", model.__tablename__

    def test_author_survives_as_null_when_the_account_goes(self) -> None:
        """SET NULL, not CASCADE: deleting a peer must not erase what they said
        on someone else's ticket — the row keeps its dated tombstone."""
        for model, column in (
            (WorkboardComment, "author_user_id"),
            (WorkboardTicketEvent, "actor_user_id"),
        ):
            fk = next(iter(model.__table__.c[column].foreign_keys))
            assert fk.ondelete == "SET NULL", model.__tablename__

    def test_the_event_log_is_never_updated(self) -> None:
        assert "updated_at" not in WorkboardTicketEvent.__table__.c
        assert "created_at" in WorkboardTicketEvent.__table__.c

    def test_a_comment_keeps_the_run_that_wrote_it(self) -> None:
        """The join key to the three ADR-263 registers."""
        assert WorkboardComment.__table__.c.run_id.nullable is True
