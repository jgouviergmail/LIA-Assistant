"""What the API contract refuses before any rule runs (ADR-276).

Pydantic owns SHAPE here, never bounds: the service enforces those from
settings and the agent manifests publish the same settings, so a
``max_length`` typed by hand would be a second authority that refuses what the
service accepts the moment an operator retunes a value (ADR-184's trap,
pointing the other way).

What shape DOES settle, and is pinned below: which fields exist, which
combinations contradict each other, and the difference between « leave this
alone » and « clear it ».
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime

import pytest
from pydantic import ValidationError

from src.domains.workboard.schemas import (
    CategoryCreate,
    CategoryUpdate,
    CommentCreate,
    MoveRequest,
    TicketCreate,
    TicketUpdate,
)

pytestmark = pytest.mark.unit


class TestOneWayToNameTheHolder:
    def test_a_peer_id_beside_an_explicit_assignee_is_refused(self) -> None:
        """The two can disagree, and the ticket would then be filed against one
        holder while the reader was told another."""
        with pytest.raises(ValidationError):
            TicketCreate(title="t", assignee="lia", assignee_user_id=uuid.uuid4())

    def test_a_peer_id_alone_is_accepted(self) -> None:
        assert TicketCreate(title="t", assignee_user_id=uuid.uuid4()).assignee == "me"

    def test_an_explicit_assignee_alone_is_accepted(self) -> None:
        assert TicketCreate(title="t", assignee="lia").assignee_user_id is None

    def test_the_same_refusal_applies_to_an_update(self) -> None:
        with pytest.raises(ValidationError):
            TicketUpdate(assignee="lia", assignee_user_id=uuid.uuid4())


class TestDatesAreSetOrCleared:
    def test_setting_and_clearing_the_same_date_is_refused(self) -> None:
        now = datetime.now(UTC)
        with pytest.raises(ValidationError):
            TicketUpdate(due_at=now, clear_due_at=True)
        with pytest.raises(ValidationError):
            TicketUpdate(start_at=now, clear_start_at=True)

    def test_clearing_alone_is_accepted(self) -> None:
        assert TicketUpdate(clear_due_at=True).clear_due_at is True

    def test_an_empty_update_is_valid(self) -> None:
        """« Change nothing » is a legitimate request, not an error."""
        update = TicketUpdate()
        assert update.title is None
        assert update.follow is None


class TestReparentingIsNotOffered:
    def test_an_update_carrying_a_parent_is_refused_outright(self) -> None:
        """A ticket's place in the hierarchy is fixed at creation. Re-parenting
        needs a cycle check creation cannot need, and nothing asked for it —
        so the field is absent and ``extra='forbid'`` makes that a refusal
        rather than a silently ignored key.
        """
        with pytest.raises(ValidationError):
            TicketUpdate(parent_id=uuid.uuid4())  # type: ignore[call-arg]

    def test_creation_still_takes_one(self) -> None:
        parent_id = uuid.uuid4()
        assert TicketCreate(title="t", parent_id=parent_id).parent_id == parent_id


class TestUnknownFieldsAreRefused:
    @pytest.mark.parametrize(
        "model",
        [TicketCreate, TicketUpdate, CommentCreate, MoveRequest, CategoryCreate, CategoryUpdate],
    )
    def test_a_typo_is_a_refusal_not_a_silent_no_op(self, model: type) -> None:
        """Without ``extra='forbid'``, ``{"prioriy": "high"}`` would be accepted
        and change nothing — the caller believing they were obeyed."""
        payload: dict[str, object] = {
            "title": "t",
            "body": "b",
            "status": "todo",
            "position": 0,
            "name": "n",
        }
        payload["definitely_not_a_field"] = 1
        with pytest.raises(ValidationError):
            model(**payload)


class TestMoveRequest:
    def test_a_negative_position_is_refused(self) -> None:
        with pytest.raises(ValidationError):
            MoveRequest(status="todo", position=-1)

    def test_position_zero_is_the_top_of_a_column(self) -> None:
        assert MoveRequest(status="todo", position=0).position == 0


class TestCategoryIsSetOrCleared:
    """A ticket's category has three states too: set, left alone, removed."""

    @pytest.mark.parametrize("model", [TicketUpdate, MoveRequest])
    def test_setting_and_clearing_in_one_request_is_refused(self, model: type) -> None:
        payload: dict[str, object] = {"category_id": uuid.uuid4(), "clear_category": True}
        if model is MoveRequest:
            payload.update(status="todo", position=0)
        with pytest.raises(ValidationError):
            model(**payload)

    def test_clearing_alone_is_accepted(self) -> None:
        assert TicketUpdate(clear_category=True).category_id is None
        assert MoveRequest(status="todo", position=0, clear_category=True).clear_category is True

    def test_a_move_says_nothing_about_the_category_by_default(self) -> None:
        """A drag inside one lane must not un-file the ticket it moves."""
        move = MoveRequest(status="todo", position=0)
        assert move.category_id is None and move.clear_category is False

    def test_a_ticket_may_be_created_straight_into_a_category(self) -> None:
        category = uuid.uuid4()
        assert TicketCreate(title="t", category_id=category).category_id == category


class TestCategoryWrites:
    def test_an_empty_patch_is_refused(self) -> None:
        """A request that changes nothing is a caller that believes it did."""
        with pytest.raises(ValidationError):
            CategoryUpdate()

    def test_a_name_or_a_position_alone_is_a_patch(self) -> None:
        assert CategoryUpdate(name="Home").position is None
        assert CategoryUpdate(position=0).name is None

    @pytest.mark.parametrize("model", [CategoryCreate, CategoryUpdate])
    def test_a_negative_position_is_refused(self, model: type) -> None:
        with pytest.raises(ValidationError):
            model(name="Home", position=-1)
