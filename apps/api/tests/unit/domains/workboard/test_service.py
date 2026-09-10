"""Every right, every bound and every transition of the board (ADR-276).

The service is where the invariants the database cannot express live (the
cascade-order trap in ``test_lifecycle_db`` is why), so this file is where they
are pinned:

- who may do what, by the caller's relation to the row (owner or peer holder);
- the bounds, checked AT the setting rather than against a literal;
- the transitions, and the events each one leaves behind;
- the two refusals that protect an account from another: a peer may not
  delegate to their own LIA, and an owner may not delegate a ticket a peer
  holds (both are the same cross-account exfiltration, from either side).
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta
from types import SimpleNamespace
from typing import Any
from unittest.mock import AsyncMock, patch

import pytest

from src.core.config import settings
from src.core.exceptions import BaseAPIException, ResourceNotFoundError
from src.domains.workboard.constants import (
    ActorKind,
    AssigneeKind,
    TicketEventKind,
    TicketStatus,
    WorkboardError,
)
from src.domains.workboard.schemas import CommentCreate, TicketCreate, TicketUpdate
from src.domains.workboard.service import WorkboardService

pytestmark = pytest.mark.unit

OWNER = uuid.uuid4()
PEER = uuid.uuid4()
STRANGER = uuid.uuid4()


def _user(user_id: uuid.UUID) -> Any:
    return SimpleNamespace(id=user_id, is_active=True)


def _ticket(**overrides: Any) -> Any:
    """A ticket row in its simplest valid shape.

    Args:
        **overrides: Any attribute to set differently.

    Returns:
        A stand-in carrying the attributes the service reads and writes.
    """
    values: dict[str, Any] = {
        "id": uuid.uuid4(),
        "owner_user_id": OWNER,
        "parent_id": None,
        "title": "Book the venue",
        "description": None,
        "status": TicketStatus.TODO.value,
        "priority": "medium",
        "start_at": None,
        "due_at": None,
        "assignee_kind": AssigneeKind.HUMAN.value,
        "assignee_user_id": None,
        "position": 0,
        "follow_owner": False,
        "follow_assignee": False,
        "created_by": ActorKind.USER.value,
        "status_changed_at": datetime.now(UTC),
        "run_count": 0,
        "run_claimed_at": None,
        "run_not_before": None,
        "last_run_outcome": None,
    }
    values.update(overrides)
    return SimpleNamespace(**values)


def _service(*, peers_enabled: bool = True, connected: bool = True) -> WorkboardService:
    """A service whose repository and peer lookup are stubbed.

    Args:
        peers_enabled: Whether the instance runs the peers feature.
        connected: Whether an ACCEPTED connection exists with the peer.

    Returns:
        The service under test.
    """
    service = WorkboardService(db=AsyncMock())
    service.repo = AsyncMock()
    # An event row comes back flushed, with the id the notification names.
    service.repo.add_event.return_value = SimpleNamespace(id=uuid.uuid4())
    service.repo.count_owned.return_value = 0
    service.repo.count_children.return_value = 0
    service.repo.next_position.return_value = 0
    service.repo.list_children.return_value = []
    service.repo.list_comments.return_value = []
    service.repo.list_events.return_value = []
    service.repo.list_column_ids.return_value = []
    service.repo.renumber_column.return_value = 0
    service._peers_enabled = lambda: peers_enabled  # type: ignore[method-assign]
    service._has_accepted_connection = AsyncMock(return_value=connected)  # type: ignore[method-assign]
    return service


def _code(exc: BaseAPIException) -> str:
    return exc.detail if isinstance(exc.detail, str) else str(exc.detail)


def _events(service: WorkboardService) -> list[str]:
    return [call.kwargs["kind"] for call in service.repo.add_event.await_args_list]


class TestCreate:
    async def test_it_lands_on_the_callers_own_board(self) -> None:
        service = _service()
        created = _ticket()
        service.repo.create = AsyncMock(return_value=created)

        ticket = await service.create(_user(OWNER), TicketCreate(title="Book the venue"))

        assert ticket is created
        payload = service.repo.create.await_args.args[0]
        assert payload["owner_user_id"] == OWNER
        assert payload["assignee_kind"] == AssigneeKind.HUMAN.value
        assert payload["assignee_user_id"] is None, "NULL means the owner holds it"
        assert payload["created_by"] == ActorKind.USER.value
        assert _events(service) == [TicketEventKind.CREATED.value]

    async def test_the_title_is_trimmed(self) -> None:
        service = _service()
        service.repo.create = AsyncMock(return_value=_ticket())
        await service.create(_user(OWNER), TicketCreate(title="  Book the venue  "))
        assert service.repo.create.await_args.args[0]["title"] == "Book the venue"

    async def test_a_blank_title_is_refused(self) -> None:
        with pytest.raises(BaseAPIException) as exc:
            await _service().create(_user(OWNER), TicketCreate(title="   "))
        assert _code(exc.value) == WorkboardError.TITLE_REQUIRED.value

    async def test_a_title_over_the_bound_is_refused(self) -> None:
        title = "x" * (settings.workboard_title_max_chars + 1)
        with pytest.raises(BaseAPIException) as exc:
            await _service().create(_user(OWNER), TicketCreate(title=title))
        assert _code(exc.value) == WorkboardError.TITLE_TOO_LONG.value

    async def test_a_title_exactly_at_the_bound_is_accepted(self) -> None:
        """Off-by-one on a published bound is a refusal the producer cannot
        predict (ADR-184)."""
        service = _service()
        service.repo.create = AsyncMock(return_value=_ticket())
        await service.create(
            _user(OWNER), TicketCreate(title="x" * settings.workboard_title_max_chars)
        )
        service.repo.create.assert_awaited_once()

    async def test_a_description_over_the_bound_is_refused(self) -> None:
        with pytest.raises(BaseAPIException) as exc:
            await _service().create(
                _user(OWNER),
                TicketCreate(
                    title="t", description="x" * (settings.workboard_description_max_chars + 1)
                ),
            )
        assert _code(exc.value) == WorkboardError.DESCRIPTION_TOO_LONG.value

    async def test_an_unknown_status_or_priority_is_refused(self) -> None:
        service = _service()
        with pytest.raises(BaseAPIException) as status_exc:
            await service.create(_user(OWNER), TicketCreate(title="t", status="parked"))
        assert _code(status_exc.value) == WorkboardError.STATUS_INVALID.value
        with pytest.raises(BaseAPIException) as priority_exc:
            await service.create(_user(OWNER), TicketCreate(title="t", priority="blocker"))
        assert _code(priority_exc.value) == WorkboardError.PRIORITY_INVALID.value

    async def test_a_due_date_before_its_start_is_refused(self) -> None:
        now = datetime.now(UTC)
        with pytest.raises(BaseAPIException) as exc:
            await _service().create(
                _user(OWNER),
                TicketCreate(title="t", start_at=now, due_at=now - timedelta(hours=1)),
            )
        assert _code(exc.value) == WorkboardError.DATES_INVERTED.value

    async def test_the_per_account_cap_is_refused_at_the_bound(self) -> None:
        service = _service()
        service.repo.count_owned.return_value = settings.workboard_max_tickets_per_user
        with pytest.raises(BaseAPIException) as exc:
            await service.create(_user(OWNER), TicketCreate(title="one more"))
        assert _code(exc.value) == WorkboardError.TOO_MANY_TICKETS.value

    async def test_one_below_the_cap_still_passes(self) -> None:
        service = _service()
        service.repo.count_owned.return_value = settings.workboard_max_tickets_per_user - 1
        service.repo.create = AsyncMock(return_value=_ticket())
        await service.create(_user(OWNER), TicketCreate(title="the last one"))
        service.repo.create.assert_awaited_once()

    async def test_it_takes_the_end_of_its_column(self) -> None:
        service = _service()
        service.repo.next_position.return_value = 4
        service.repo.create = AsyncMock(return_value=_ticket())
        await service.create(_user(OWNER), TicketCreate(title="t"))
        assert service.repo.create.await_args.args[0]["position"] == 4

    async def test_follow_applies_to_the_creator_side_only(self) -> None:
        service = _service()
        service.repo.create = AsyncMock(return_value=_ticket())
        await service.create(_user(OWNER), TicketCreate(title="t", follow=True))
        payload = service.repo.create.await_args.args[0]
        assert payload["follow_owner"] is True
        assert payload["follow_assignee"] is False


class TestCreateAssignment:
    async def test_lia_stays_on_the_owner_account(self) -> None:
        """A LIA ticket runs on ``assignee_user_id``'s account, and NULL means
        the owner — so a LIA ticket is always the owner's own spend."""
        service = _service()
        service.repo.create = AsyncMock(return_value=_ticket())
        await service.create(_user(OWNER), TicketCreate(title="research", assignee="lia"))
        payload = service.repo.create.await_args.args[0]
        assert payload["assignee_kind"] == AssigneeKind.LIA.value
        assert payload["assignee_user_id"] is None

    async def test_a_peer_assignment_needs_an_accepted_connection(self) -> None:
        service = _service(connected=False)
        with pytest.raises(BaseAPIException) as exc:
            await service.create(_user(OWNER), TicketCreate(title="t", assignee_user_id=PEER))
        assert _code(exc.value) == WorkboardError.ASSIGNEE_NOT_CONNECTED.value

    async def test_a_connected_peer_is_stored_as_the_holder(self) -> None:
        service = _service()
        service.repo.create = AsyncMock(return_value=_ticket())
        await service.create(_user(OWNER), TicketCreate(title="t", assignee_user_id=PEER))
        payload = service.repo.create.await_args.args[0]
        assert payload["assignee_kind"] == AssigneeKind.HUMAN.value
        assert payload["assignee_user_id"] == PEER

    async def test_a_peer_assignment_is_refused_when_the_instance_disabled_peers(self) -> None:
        service = _service(peers_enabled=False)
        with pytest.raises(BaseAPIException) as exc:
            await service.create(_user(OWNER), TicketCreate(title="t", assignee_user_id=PEER))
        assert _code(exc.value) == WorkboardError.PEERS_DISABLED.value

    async def test_assigning_to_myself_by_id_needs_no_connection(self) -> None:
        """The client may spell « me » as my own id; that is not a peer."""
        service = _service(connected=False)
        service.repo.create = AsyncMock(return_value=_ticket())
        await service.create(_user(OWNER), TicketCreate(title="t", assignee_user_id=OWNER))
        assert service.repo.create.await_args.args[0]["assignee_user_id"] is None


class TestCreateChildren:
    async def test_a_child_of_a_child_is_refused(self) -> None:
        service = _service()
        child = _ticket(parent_id=uuid.uuid4())
        service.repo.get_visible.return_value = child
        with pytest.raises(BaseAPIException) as exc:
            await service.create(_user(OWNER), TicketCreate(title="t", parent_id=child.id))
        assert _code(exc.value) == WorkboardError.DEPTH_EXCEEDED.value

    async def test_a_child_under_a_ticket_i_only_hold_is_refused(self) -> None:
        """Decomposition is the owner's; a holder adding children to someone
        else's ticket would be writing on their board."""
        service = _service()
        service.repo.get_visible.return_value = _ticket(owner_user_id=PEER, assignee_user_id=OWNER)
        with pytest.raises(BaseAPIException) as exc:
            await service.create(_user(OWNER), TicketCreate(title="t", parent_id=uuid.uuid4()))
        assert _code(exc.value) == WorkboardError.PARENT_NOT_OWNED.value

    async def test_an_unknown_parent_is_a_404(self) -> None:
        service = _service()
        service.repo.get_visible.return_value = None
        with pytest.raises(ResourceNotFoundError):
            await service.create(_user(OWNER), TicketCreate(title="t", parent_id=uuid.uuid4()))

    async def test_the_children_cap_is_refused_at_the_bound(self) -> None:
        service = _service()
        service.repo.get_visible.return_value = _ticket()
        service.repo.count_children.return_value = settings.workboard_max_children_per_ticket
        with pytest.raises(BaseAPIException) as exc:
            await service.create(_user(OWNER), TicketCreate(title="t", parent_id=uuid.uuid4()))
        assert _code(exc.value) == WorkboardError.TOO_MANY_CHILDREN.value

    async def test_a_child_is_created_under_its_parent(self) -> None:
        service = _service()
        parent = _ticket()
        service.repo.get_visible.return_value = parent
        service.repo.create = AsyncMock(return_value=_ticket(parent_id=parent.id))
        await service.create(
            _user(OWNER), TicketCreate(title="Call the caterer", parent_id=parent.id)
        )
        assert service.repo.create.await_args.args[0]["parent_id"] == parent.id


class TestPeerRights:
    """What a peer HOLDER may and may not do (spec §8)."""

    @staticmethod
    def _held() -> Any:
        return _ticket(assignee_user_id=PEER)

    async def test_a_peer_may_move_and_reprioritise(self) -> None:
        service = _service()
        ticket = self._held()
        service.repo.get_visible.return_value = ticket
        await service.update(
            _user(PEER), ticket.id, TicketUpdate(status="in_progress", priority="high")
        )
        assert ticket.status == "in_progress"
        assert ticket.priority == "high"

    async def test_a_peer_may_comment(self) -> None:
        service = _service()
        ticket = self._held()
        service.repo.get_visible.return_value = ticket
        await service.comment(_user(PEER), ticket.id, CommentCreate(body="On it."))
        assert service.repo.add_comment.await_args.kwargs["author_kind"] == ActorKind.PEER.value

    async def test_a_peer_may_not_rewrite_the_owners_words(self) -> None:
        service = _service()
        ticket = self._held()
        service.repo.get_visible.return_value = ticket
        for update in (TicketUpdate(title="mine now"), TicketUpdate(description="rewritten")):
            with pytest.raises(BaseAPIException) as exc:
                await service.update(_user(PEER), ticket.id, update)
            assert _code(exc.value) == WorkboardError.PEER_CANNOT_EDIT_FIELD.value

    async def test_a_peer_may_not_delete(self) -> None:
        service = _service()
        ticket = self._held()
        service.repo.get_visible.return_value = ticket
        with pytest.raises(BaseAPIException) as exc:
            await service.delete(_user(PEER), ticket.id)
        assert _code(exc.value) == WorkboardError.PEER_CANNOT_DELETE.value

    async def test_a_peer_may_hand_the_ticket_back(self) -> None:
        service = _service()
        ticket = self._held()
        ticket.follow_assignee = True
        service.repo.get_visible.return_value = ticket
        await service.update(_user(PEER), ticket.id, TicketUpdate(assignee_user_id=OWNER))
        assert ticket.assignee_user_id is None
        assert ticket.assignee_kind == AssigneeKind.HUMAN.value
        assert ticket.follow_assignee is False

    async def test_a_peer_may_not_pass_it_to_a_third_person(self) -> None:
        service = _service()
        ticket = self._held()
        service.repo.get_visible.return_value = ticket
        with pytest.raises(BaseAPIException) as exc:
            await service.update(_user(PEER), ticket.id, TicketUpdate(assignee_user_id=STRANGER))
        assert _code(exc.value) == WorkboardError.PEER_CANNOT_REASSIGN.value

    async def test_a_peer_may_not_hand_it_to_their_own_lia(self) -> None:
        """The instruction is the OWNER's words; running it unattended with the
        peer's tools would put the peer's data in a comment the owner reads."""
        service = _service()
        ticket = self._held()
        service.repo.get_visible.return_value = ticket
        with pytest.raises(BaseAPIException) as exc:
            await service.update(_user(PEER), ticket.id, TicketUpdate(assignee="lia"))
        assert _code(exc.value) == WorkboardError.CROSS_ACCOUNT_DELEGATION.value

    async def test_the_owner_may_not_delegate_a_ticket_a_peer_holds(self) -> None:
        """The same refusal from the other side: LIA on a foreign-held ticket
        would be the peer's LIA, running the owner's instruction."""
        service = _service()
        ticket = self._held()
        service.repo.get_visible.return_value = ticket
        with pytest.raises(BaseAPIException) as exc:
            await service.update(_user(OWNER), ticket.id, TicketUpdate(assignee="lia"))
        assert _code(exc.value) == WorkboardError.CROSS_ACCOUNT_DELEGATION.value

    async def test_the_owner_takes_it_back_then_may_delegate(self) -> None:
        service = _service()
        ticket = self._held()
        service.repo.get_visible.return_value = ticket
        await service.update(_user(OWNER), ticket.id, TicketUpdate(assignee="me"))
        assert ticket.assignee_user_id is None
        await service.update(_user(OWNER), ticket.id, TicketUpdate(assignee="lia"))
        assert ticket.assignee_kind == AssigneeKind.LIA.value


class TestFollowFlags:
    async def test_each_side_sets_its_own(self) -> None:
        service = _service()
        ticket = _ticket(assignee_user_id=PEER)
        service.repo.get_visible.return_value = ticket

        await service.update(_user(PEER), ticket.id, TicketUpdate(follow=True))
        assert ticket.follow_assignee is True
        assert ticket.follow_owner is False

        await service.update(_user(OWNER), ticket.id, TicketUpdate(follow=True))
        assert ticket.follow_owner is True

    async def test_reassignment_clears_the_holders_flag(self) -> None:
        """The next holder never inherits somebody else's subscription."""
        service = _service()
        ticket = _ticket(assignee_user_id=PEER, follow_assignee=True, follow_owner=True)
        service.repo.get_visible.return_value = ticket
        await service.update(_user(OWNER), ticket.id, TicketUpdate(assignee="me"))
        assert ticket.follow_assignee is False
        assert ticket.follow_owner is True, "the owner's own choice is untouched"


class TestHandingATicketOver:
    """The new holder is told — nobody can follow a ticket they do not know."""

    @staticmethod
    def _sent() -> Any:
        from unittest.mock import AsyncMock

        return AsyncMock(return_value=True)

    async def test_the_peer_is_told_they_now_hold_it(self) -> None:
        from unittest.mock import patch

        service = _service()
        ticket = _ticket()
        service.repo.get_visible.return_value = ticket
        service.db.get = AsyncMock(return_value=SimpleNamespace(id=PEER, language="fr"))
        sent = self._sent()

        with (
            patch.object(service, "_has_accepted_connection", AsyncMock(return_value=True)),
            patch("src.core.config.settings.peers_enabled", True, create=True),
            patch("src.domains.shared.proactive_sink.send_proactive_notification", sent),
        ):
            await service.update(_user(OWNER), ticket.id, TicketUpdate(assignee_user_id=PEER))

        sent.assert_awaited_once()
        call = sent.await_args.kwargs
        assert call["task_type"] == "workboard"
        assert call["metadata"]["event"] == "assigned"
        assert "Book the venue" in call["content"]
        assert call["occurrence"] == "assigned"
        # The act's own run: the ASSIGNED event, a row the registers can join.
        assert call["run_id"] == f"ticket-event:{service.repo.add_event.return_value.id}"

    async def test_each_handover_is_its_own_act(self) -> None:
        """A second handover of the same ticket must not be lost as a replay
        of the first under the register's idempotency key."""
        from unittest.mock import patch

        service = _service()
        ticket = _ticket(assignee_user_id=PEER)
        service.db.get = AsyncMock(return_value=SimpleNamespace(id=PEER, language="fr"))
        sent = self._sent()

        with patch("src.domains.shared.proactive_sink.send_proactive_notification", sent):
            await service._announce_assignment(ticket, _user(OWNER), event_id=uuid.uuid4())
            await service._announce_assignment(ticket, _user(OWNER), event_id=uuid.uuid4())

        runs = [c.kwargs["run_id"] for c in sent.await_args_list]
        assert len(runs) == 2
        assert runs[0] != runs[1]
        assert all(run.startswith("ticket-event:") for run in runs)
        assert {c.kwargs["occurrence"] for c in sent.await_args_list} == {"assigned"}

    async def test_taking_a_ticket_back_tells_nobody(self) -> None:
        """A NULL assignee means the owner holds it; there is no new holder."""
        from unittest.mock import patch

        service = _service()
        ticket = _ticket(assignee_user_id=PEER)
        service.repo.get_visible.return_value = ticket
        sent = self._sent()

        with patch("src.domains.shared.proactive_sink.send_proactive_notification", sent):
            await service.update(_user(OWNER), ticket.id, TicketUpdate(assignee="me"))

        sent.assert_not_awaited()

    async def test_handing_it_to_lia_tells_nobody(self) -> None:
        from unittest.mock import patch

        service = _service()
        ticket = _ticket()
        service.repo.get_visible.return_value = ticket
        sent = self._sent()

        with patch("src.domains.shared.proactive_sink.send_proactive_notification", sent):
            await service.update(_user(OWNER), ticket.id, TicketUpdate(assignee="lia"))

        sent.assert_not_awaited()

    async def test_a_notification_that_cannot_leave_never_undoes_the_assignment(self) -> None:
        """The board already holds it, and the person asked for it."""
        from unittest.mock import patch

        service = _service()
        ticket = _ticket()
        service.repo.get_visible.return_value = ticket
        service.db.get = AsyncMock(return_value=SimpleNamespace(id=PEER, language="fr"))

        with (
            patch.object(service, "_has_accepted_connection", AsyncMock(return_value=True)),
            patch("src.core.config.settings.peers_enabled", True, create=True),
            patch(
                "src.domains.shared.proactive_sink.send_proactive_notification",
                AsyncMock(return_value=False),
            ),
        ):
            await service.update(_user(OWNER), ticket.id, TicketUpdate(assignee_user_id=PEER))

        assert ticket.assignee_user_id == PEER


class TestTransitions:
    async def test_any_column_to_any_column_by_a_person(self) -> None:
        """Only a RUN's transitions are conditional; a person is never refused
        a move on their own board."""
        service = _service()
        ticket = _ticket(status=TicketStatus.DONE.value)
        before = ticket.status_changed_at
        service.repo.get_visible.return_value = ticket
        await service.update(_user(OWNER), ticket.id, TicketUpdate(status="idea"))
        assert ticket.status == "idea"
        assert ticket.status_changed_at >= before
        assert TicketEventKind.STATUS_CHANGED.value in _events(service)

    async def test_a_status_that_does_not_change_leaves_no_event(self) -> None:
        service = _service()
        ticket = _ticket(status=TicketStatus.TODO.value)
        service.repo.get_visible.return_value = ticket
        await service.update(_user(OWNER), ticket.id, TicketUpdate(status="todo"))
        assert _events(service) == []

    async def test_an_unknown_status_is_refused(self) -> None:
        service = _service()
        service.repo.get_visible.return_value = _ticket()
        with pytest.raises(BaseAPIException) as exc:
            await service.update(_user(OWNER), uuid.uuid4(), TicketUpdate(status="parked"))
        assert _code(exc.value) == WorkboardError.STATUS_INVALID.value

    async def test_clearing_a_date_is_explicit(self) -> None:
        service = _service()
        ticket = _ticket(due_at=datetime.now(UTC))
        service.repo.get_visible.return_value = ticket
        await service.update(_user(OWNER), ticket.id, TicketUpdate(clear_due_at=True))
        assert ticket.due_at is None
        assert TicketEventKind.DATES_CHANGED.value in _events(service)

    async def test_an_inverted_date_pair_is_refused_on_update_too(self) -> None:
        service = _service()
        now = datetime.now(UTC)
        ticket = _ticket(start_at=now)
        service.repo.get_visible.return_value = ticket
        with pytest.raises(BaseAPIException) as exc:
            await service.update(
                _user(OWNER), ticket.id, TicketUpdate(due_at=now - timedelta(days=1))
            )
        assert _code(exc.value) == WorkboardError.DATES_INVERTED.value


class TestMove:
    async def test_it_inserts_at_the_asked_position(self) -> None:
        service = _service()
        ticket = _ticket(status=TicketStatus.TODO.value)
        others = [uuid.uuid4(), uuid.uuid4()]
        service.repo.get_visible.return_value = ticket
        service.repo.list_column_ids.return_value = [others[0], others[1]]

        await service.move(_user(OWNER), ticket.id, "in_progress", 1)

        ordered = service.repo.renumber_column.await_args.args[2]
        assert ordered == [others[0], ticket.id, others[1]]
        assert ticket.status == "in_progress"
        assert ticket.position == 1

    async def test_a_position_past_the_end_lands_last(self) -> None:
        service = _service()
        ticket = _ticket()
        service.repo.get_visible.return_value = ticket
        service.repo.list_column_ids.return_value = [uuid.uuid4()]
        await service.move(_user(OWNER), ticket.id, "todo", 99)
        assert service.repo.renumber_column.await_args.args[2][-1] == ticket.id

    async def test_a_move_within_one_column_does_not_re_stamp_the_status(self) -> None:
        """``status_changed_at`` drives the closed-ticket filter and the
        waiting-too-long nudge; bumping it on a reorder would hide a ticket."""
        service = _service()
        stamped = datetime.now(UTC) - timedelta(days=5)
        ticket = _ticket(status=TicketStatus.TODO.value, status_changed_at=stamped)
        service.repo.get_visible.return_value = ticket
        service.repo.list_column_ids.return_value = [ticket.id]
        await service.move(_user(OWNER), ticket.id, "todo", 0)
        assert ticket.status_changed_at == stamped
        assert _events(service) == []

    async def test_the_column_it_renumbers_is_the_owners(self) -> None:
        """Positions live on the OWNER's board; a peer moving a ticket must not
        renumber their own column with somebody else's ids."""
        service = _service()
        ticket = _ticket(assignee_user_id=PEER)
        service.repo.get_visible.return_value = ticket
        await service.move(_user(PEER), ticket.id, "in_progress", 0)
        assert service.repo.renumber_column.await_args.args[0] == OWNER


class TestRunNow:
    async def test_it_gives_the_ticket_a_fresh_run(self) -> None:
        """After three reaped claims `run_attempts` sits at the cap and the scan
        never offers the ticket again; a person's explicit ask must not move
        it to `todo` and change nothing."""
        service = _service()
        ticket = _ticket(
            assignee_kind=AssigneeKind.LIA.value,
            status=TicketStatus.IN_PROGRESS.value,
            run_attempts=3,
            run_not_before=datetime.now(UTC),
        )
        service.repo.get_visible.return_value = ticket

        await service.run_now(_user(OWNER), ticket.id)

        assert ticket.run_attempts == 0
        assert ticket.run_not_before is None
        assert ticket.status == TicketStatus.TODO.value

    async def test_it_needs_a_lia_assignee(self) -> None:
        service = _service()
        service.repo.get_visible.return_value = _ticket()
        with pytest.raises(BaseAPIException) as exc:
            await service.run_now(_user(OWNER), uuid.uuid4())
        assert _code(exc.value) == WorkboardError.RUN_NOW_REQUIRES_LIA.value

    async def test_it_is_refused_at_the_runs_cap(self) -> None:
        """The cap bounds the hidden run transcripts a board accumulates."""
        service = _service()
        service.repo.get_visible.return_value = _ticket(
            assignee_kind=AssigneeKind.LIA.value,
            run_count=settings.workboard_max_runs_per_ticket,
        )
        with pytest.raises(BaseAPIException) as exc:
            await service.run_now(_user(OWNER), uuid.uuid4())
        assert _code(exc.value) == WorkboardError.MAX_RUNS_REACHED.value

    async def test_it_arms_the_ticket_for_the_next_sweep(self) -> None:
        service = _service()
        ticket = _ticket(
            assignee_kind=AssigneeKind.LIA.value,
            status=TicketStatus.VALIDATING.value,
            start_at=datetime.now(UTC) + timedelta(days=3),
            run_not_before=datetime.now(UTC) + timedelta(hours=1),
        )
        service.repo.get_visible.return_value = ticket
        await service.run_now(_user(OWNER), ticket.id)
        assert ticket.status == TicketStatus.TODO.value
        assert ticket.start_at is None
        assert ticket.run_not_before is None

    async def test_a_peer_holder_cannot_start_a_run(self) -> None:
        """A LIA ticket is never peer-held (cross-account), so this can only be
        a human-held one — and « run now » on it is meaningless."""
        service = _service()
        service.repo.get_visible.return_value = _ticket(assignee_user_id=PEER)
        with pytest.raises(BaseAPIException) as exc:
            await service.run_now(_user(PEER), uuid.uuid4())
        assert _code(exc.value) == WorkboardError.RUN_NOW_REQUIRES_LIA.value


class TestComments:
    async def test_a_comment_over_the_bound_is_refused(self) -> None:
        service = _service()
        service.repo.get_visible.return_value = _ticket()
        with pytest.raises(BaseAPIException) as exc:
            await service.comment(
                _user(OWNER),
                uuid.uuid4(),
                CommentCreate(body="x" * (settings.workboard_comment_max_chars + 1)),
            )
        assert _code(exc.value) == WorkboardError.COMMENT_TOO_LONG.value

    async def test_an_empty_comment_is_refused(self) -> None:
        service = _service()
        service.repo.get_visible.return_value = _ticket()
        with pytest.raises(BaseAPIException) as exc:
            await service.comment(_user(OWNER), uuid.uuid4(), CommentCreate(body="   "))
        assert _code(exc.value) == WorkboardError.COMMENT_REQUIRED.value

    async def test_the_owner_is_authored_as_user(self) -> None:
        service = _service()
        service.repo.get_visible.return_value = _ticket()
        await service.comment(_user(OWNER), uuid.uuid4(), CommentCreate(body="Noted."))
        assert service.repo.add_comment.await_args.kwargs["author_kind"] == ActorKind.USER.value


class TestVisibilityAndDelete:
    async def test_an_unknown_or_foreign_ticket_is_a_404(self) -> None:
        service = _service()
        service.repo.get_visible.return_value = None
        with pytest.raises(ResourceNotFoundError):
            await service.get(_user(STRANGER), uuid.uuid4())

    async def test_delete_reports_what_it_took(self) -> None:
        service = _service()
        ticket = _ticket()
        service.repo.get_visible.return_value = ticket
        service.repo.count_children.return_value = 2
        assert await service.delete(_user(OWNER), ticket.id) == 3
        service.repo.delete.assert_awaited_once_with(ticket)

    async def test_get_bundles_children_comments_and_history(self) -> None:
        service = _service()
        ticket = _ticket()
        service.repo.get_visible.return_value = ticket
        service.repo.list_children.return_value = ["child"]
        service.repo.list_comments.return_value = ["comment"]
        service.repo.list_events.return_value = ["event"]
        bundle = await service.get(_user(OWNER), ticket.id)
        assert bundle.ticket is ticket
        assert bundle.children == ["child"]
        assert bundle.comments == ["comment"]
        assert bundle.events == ["event"]


class TestReferenceResolution:
    async def test_an_id_resolves_directly(self) -> None:
        service = _service()
        ticket = _ticket()
        service.repo.get_visible.return_value = ticket
        assert await service.resolve_reference(OWNER, str(ticket.id)) is ticket

    async def test_a_unique_title_resolves(self) -> None:
        service = _service()
        ticket = _ticket()
        service.repo.find_by_title.return_value = [ticket]
        assert await service.resolve_reference(OWNER, "Book the venue") is ticket

    async def test_two_tickets_worded_alike_are_refused_not_guessed(self) -> None:
        """A false positive hands one ticket's fate to a question about another."""
        service = _service()
        service.repo.find_by_title.return_value = [_ticket(), _ticket()]
        with pytest.raises(BaseAPIException) as exc:
            await service.resolve_reference(OWNER, "Book the venue")
        assert _code(exc.value) == WorkboardError.AMBIGUOUS_REFERENCE.value

    async def test_no_match_is_a_404(self) -> None:
        service = _service()
        service.repo.find_by_title.return_value = []
        with pytest.raises(ResourceNotFoundError):
            await service.resolve_reference(OWNER, "nothing like this")

    async def test_a_uuid_naming_a_foreign_ticket_is_a_404_not_a_title_search(self) -> None:
        """Falling back to a title search on a well-formed but invisible id
        would let a stranger learn that an id exists."""
        service = _service()
        service.repo.get_visible.return_value = None
        with pytest.raises(ResourceNotFoundError):
            await service.resolve_reference(STRANGER, str(uuid.uuid4()))
        service.repo.find_by_title.assert_not_awaited()


class TestReleasePair:
    async def test_it_hands_back_every_ticket_of_a_removed_connection(self) -> None:
        service = _service()
        held = _ticket(assignee_user_id=PEER, follow_assignee=True)

        async def _held(owner_id: uuid.UUID, holder_id: uuid.UUID) -> list[Any]:
            """Direction-aware, like the repository: a ticket belongs to ONE
            direction of the pair, and a blind stub would double every row."""
            return [held] if (owner_id, holder_id) == (OWNER, PEER) else []

        service.repo.list_held_between = AsyncMock(side_effect=_held)

        released = await service.release_pair(OWNER, PEER)

        assert released == [held]
        assert held.assignee_user_id is None
        assert held.assignee_kind == AssigneeKind.HUMAN.value
        assert held.follow_assignee is False
        assert _events(service) == [TicketEventKind.ASSIGNED.value]

    async def test_it_looks_at_both_directions_of_the_pair(self) -> None:
        """A connection is one row for two people: each may hold the other's
        tickets, and removing it must release both sides."""
        service = _service()
        service.repo.list_held_between.return_value = []
        await service.release_pair(OWNER, PEER)
        calls = {call.args for call in service.repo.list_held_between.await_args_list}
        assert calls == {(OWNER, PEER), (PEER, OWNER)}

    async def test_the_release_is_authored_by_lia_not_by_a_person(self) -> None:
        service = _service()
        service.repo.list_held_between.return_value = [_ticket(assignee_user_id=PEER)]
        await service.release_pair(OWNER, PEER)
        event = service.repo.add_event.await_args.kwargs
        assert event["actor_kind"] == ActorKind.LIA.value
        assert event["actor_user_id"] is None
        assert event["payload"]["reason"] == "connection_removed"


def _confirming(**overrides: Any) -> Any:
    """A ticket LIA handed back with a draft to confirm (lot 7)."""
    values: dict[str, Any] = {
        "status": TicketStatus.CONFIRMING.value,
        "assignee_kind": AssigneeKind.HUMAN.value,
        "assignee_user_id": None,
        "pending_action": {
            "draft_id": "draft_1",
            "draft_type": "tool_call",
            "draft_content": {"tool_name": "mcp_x_delete", "tool_args": {"target": "a"}},
            "tool_name": "mcp_x_delete",
            "question": "Je supprime a ?",
            "approved": False,
        },
        "last_run_at": datetime.now(UTC) - timedelta(hours=1),
        "run_count": 1,
        "run_attempts": 0,
    }
    values.update(overrides)
    return _ticket(**values)


def _note(body: str) -> Any:
    return SimpleNamespace(body=body, author_user_id=OWNER, author_kind=ActorKind.USER.value)


def _payloads(service: WorkboardService) -> list[dict[str, Any]]:
    return [call.kwargs["payload"] for call in service.repo.add_event.await_args_list]


class TestAnsweringOnTheTicket:
    """Lot 7: handing a ticket LIA is waiting on back to LIA READS the answer."""

    async def test_an_approval_arms_the_replay(self) -> None:
        service = _service()
        ticket = _confirming()
        service.repo.get_visible.return_value = ticket
        service.repo.owner_notes_since.return_value = [_note("Oui, vas-y !")]

        await service.update(_user(OWNER), ticket.id, TicketUpdate(assignee="lia"))

        assert ticket.status == TicketStatus.TODO.value
        assert ticket.assignee_kind == AssigneeKind.LIA.value
        assert ticket.pending_action["approved"] is True
        assert ticket.pending_action["draft_id"] == "draft_1"
        assert ticket.run_attempts == 0
        assert ticket.run_not_before is None
        assert _events(service) == ["status_changed", "assigned"]
        assert [payload["reason"] for payload in _payloads(service)] == ["approve", "approve"]
        assert _payloads(service)[0] == {
            "from": "confirming",
            "to": "todo",
            "reason": "approve",
        }

    async def test_a_refusal_closes_the_ticket_and_keeps_it_with_the_person(self) -> None:
        """« Terminé » closes it and the history's ``reason`` says « refusée »:
        the board has no « Annulé » column since 2026-09-09."""
        service = _service()
        ticket = _confirming()
        service.repo.get_visible.return_value = ticket
        service.repo.owner_notes_since.return_value = [_note("Non merci.")]

        await service.update(_user(OWNER), ticket.id, TicketUpdate(assignee="lia"))

        assert ticket.status == TicketStatus.DONE.value
        assert _payloads(service)[0]["reason"] == "refuse"
        assert ticket.assignee_kind == AssigneeKind.HUMAN.value
        assert ticket.assignee_user_id is None
        assert ticket.pending_action is None
        assert _events(service) == ["status_changed"]
        assert _payloads(service)[0]["reason"] == "refuse"

    async def test_an_amendment_drops_the_draft_and_hands_over(self) -> None:
        """The words reach the next brief as the owner's notes; LIA re-reads."""
        service = _service()
        ticket = _confirming()
        service.repo.get_visible.return_value = ticket
        service.repo.owner_notes_since.return_value = [_note("Oui mais envoie plutôt à Paul")]

        await service.update(_user(OWNER), ticket.id, TicketUpdate(assignee="lia"))

        assert ticket.status == TicketStatus.TODO.value
        assert ticket.assignee_kind == AssigneeKind.LIA.value
        assert ticket.pending_action is None
        assert [payload["reason"] for payload in _payloads(service)] == ["amend", "amend"]

    async def test_the_latest_note_since_the_last_run_is_the_answer(self) -> None:
        service = _service()
        ticket = _confirming()
        service.repo.get_visible.return_value = ticket
        service.repo.owner_notes_since.return_value = [_note("ok")]

        await service.update(_user(OWNER), ticket.id, TicketUpdate(assignee="lia"))

        call = service.repo.owner_notes_since.await_args
        assert call.args == (ticket.id, OWNER)
        assert call.kwargs == {"since": ticket.last_run_at, "limit": 1}

    async def test_a_handover_without_a_word_is_refused(self) -> None:
        """Running without an answer would only ask again, at the price of a run."""
        service = _service()
        ticket = _confirming()
        service.repo.get_visible.return_value = ticket
        service.repo.owner_notes_since.return_value = []

        with pytest.raises(BaseAPIException) as exc:
            await service.update(_user(OWNER), ticket.id, TicketUpdate(assignee="lia"))

        assert _code(exc.value) == WorkboardError.ANSWER_REQUIRED.value
        assert ticket.status == TicketStatus.CONFIRMING.value
        assert ticket.assignee_kind == AssigneeKind.HUMAN.value
        assert _events(service) == []

    async def test_an_approval_past_the_runs_cap_is_refused(self) -> None:
        service = _service()
        ticket = _confirming(run_count=settings.workboard_max_runs_per_ticket)
        service.repo.get_visible.return_value = ticket
        service.repo.owner_notes_since.return_value = [_note("oui")]

        with pytest.raises(BaseAPIException) as exc:
            await service.update(_user(OWNER), ticket.id, TicketUpdate(assignee="lia"))

        assert _code(exc.value) == WorkboardError.MAX_RUNS_REACHED.value
        assert ticket.status == TicketStatus.CONFIRMING.value

    async def test_a_refusal_is_never_refused_by_the_cap(self) -> None:
        service = _service()
        ticket = _confirming(run_count=settings.workboard_max_runs_per_ticket)
        service.repo.get_visible.return_value = ticket
        service.repo.owner_notes_since.return_value = [_note("non")]

        await service.update(_user(OWNER), ticket.id, TicketUpdate(assignee="lia"))

        assert ticket.status == TicketStatus.DONE.value

    async def test_a_peer_cannot_answer_for_the_owner(self) -> None:
        """A holder handing the ticket to LIA is the cross-account refusal it
        always was; their comments are never read as the answer."""
        service = _service()
        ticket = _confirming(assignee_user_id=PEER)
        service.repo.get_visible.return_value = ticket

        with pytest.raises(BaseAPIException) as exc:
            await service.update(_user(PEER), ticket.id, TicketUpdate(assignee="lia"))

        assert _code(exc.value) == WorkboardError.CROSS_ACCOUNT_DELEGATION.value
        service.repo.owner_notes_since.assert_not_awaited()

    async def test_a_ticket_not_waiting_on_an_answer_is_handed_over_as_before(self) -> None:
        service = _service()
        ticket = _ticket(status=TicketStatus.TODO.value)
        service.repo.get_visible.return_value = ticket

        await service.update(_user(OWNER), ticket.id, TicketUpdate(assignee="lia"))

        service.repo.owner_notes_since.assert_not_awaited()
        assert ticket.assignee_kind == AssigneeKind.LIA.value
        assert "reason" not in _payloads(service)[0]

    async def test_handing_a_confirming_ticket_to_a_peer_keeps_the_question(self) -> None:
        service = _service()
        ticket = _confirming()
        service.repo.get_visible.return_value = ticket
        service.db.get = AsyncMock(return_value=SimpleNamespace(id=PEER, language="fr"))

        with (
            patch("src.core.config.settings.peers_enabled", True, create=True),
            patch("src.domains.shared.proactive_sink.send_proactive_notification", AsyncMock()),
        ):
            await service.update(_user(OWNER), ticket.id, TicketUpdate(assignee_user_id=PEER))

        assert ticket.status == TicketStatus.CONFIRMING.value
        assert ticket.pending_action is not None
        service.repo.owner_notes_since.assert_not_awaited()

    async def test_a_ticket_parked_in_the_column_by_hand_is_handed_over_as_before(self) -> None:
        """No draft on the row means no question to answer: a person who moved
        a ticket there themselves hands it to LIA like any other."""
        service = _service()
        ticket = _confirming(pending_action=None)
        service.repo.get_visible.return_value = ticket

        await service.update(_user(OWNER), ticket.id, TicketUpdate(assignee="lia"))

        service.repo.owner_notes_since.assert_not_awaited()
        assert ticket.assignee_kind == AssigneeKind.LIA.value
        assert ticket.status == TicketStatus.CONFIRMING.value

    @pytest.mark.parametrize("destination", ["todo", "in_progress", "validating", "done"])
    async def test_moving_a_confirming_ticket_anywhere_drops_the_draft(
        self, destination: str
    ) -> None:
        """Whatever the column, the question is no longer asked."""
        service = _service()
        ticket = _confirming()
        service.repo.get_visible.return_value = ticket
        service.repo.list_column_ids.return_value = []

        await service.move(_user(OWNER), ticket.id, destination, 0)

        assert ticket.status == destination
        assert ticket.pending_action is None
        assert "reason" not in _payloads(service)[0]


class TestTheCommentIsTheAnswer:
    """2026-09-09: writing the answer IS answering — no second gesture.

    A ticket left in « à confirmer » with the answer already written on it is
    the exact shape of work that never moves, and asking for the ticket back as
    well was one decision spread over two gestures.
    """

    async def test_an_approval_moves_it_and_hands_it_to_lia(self) -> None:
        service = _service()
        ticket = _confirming()
        service.repo.get_visible.return_value = ticket

        await service.comment(_user(OWNER), ticket.id, CommentCreate(body="Oui, vas-y"))

        assert ticket.status == TicketStatus.TODO.value
        assert ticket.assignee_kind == AssigneeKind.LIA.value
        assert ticket.pending_action["approved"] is True
        assert ticket.run_attempts == 0
        assert _events(service) == ["status_changed", "assigned"]
        assert [payload.get("reason") for payload in _payloads(service)] == ["approve", "approve"]

    async def test_a_refusal_closes_it_and_keeps_it_here(self) -> None:
        service = _service()
        ticket = _confirming()
        service.repo.get_visible.return_value = ticket

        await service.comment(_user(OWNER), ticket.id, CommentCreate(body="non merci"))

        assert ticket.status == TicketStatus.DONE.value
        assert ticket.assignee_kind == AssigneeKind.HUMAN.value
        assert ticket.pending_action is None
        assert _events(service) == ["status_changed"]

    async def test_an_amendment_hands_it_over_with_the_draft_dropped(self) -> None:
        service = _service()
        ticket = _confirming()
        service.repo.get_visible.return_value = ticket

        await service.comment(
            _user(OWNER), ticket.id, CommentCreate(body="Oui mais envoie plutôt à Paul")
        )

        assert ticket.status == TicketStatus.TODO.value
        assert ticket.assignee_kind == AssigneeKind.LIA.value
        assert ticket.pending_action is None

    async def test_the_comment_itself_is_still_written(self) -> None:
        """The answer moves the ticket AND stays on the thread: the next brief
        reads it as the owner's own words."""
        service = _service()
        ticket = _confirming()
        service.repo.get_visible.return_value = ticket

        await service.comment(_user(OWNER), ticket.id, CommentCreate(body="oui"))

        assert service.repo.add_comment.await_args.kwargs["body"] == "oui"

    async def test_an_ordinary_comment_on_an_ordinary_ticket_moves_nothing(self) -> None:
        service = _service()
        ticket = _ticket(status=TicketStatus.IN_PROGRESS.value)
        service.repo.get_visible.return_value = ticket

        await service.comment(_user(OWNER), ticket.id, CommentCreate(body="oui"))

        assert ticket.status == TicketStatus.IN_PROGRESS.value
        assert _events(service) == []

    async def test_a_ticket_parked_in_the_column_by_hand_moves_nothing(self) -> None:
        """No draft on the row means no question: a comment is just a comment."""
        service = _service()
        ticket = _confirming(pending_action=None)
        service.repo.get_visible.return_value = ticket

        await service.comment(_user(OWNER), ticket.id, CommentCreate(body="oui"))

        assert ticket.status == TicketStatus.CONFIRMING.value
        assert _events(service) == []

    async def test_only_the_owner_answers(self) -> None:
        """A holder's words are a stranger's, from the brief's point of view."""
        service = _service()
        ticket = _confirming(assignee_user_id=PEER)
        service.repo.get_visible.return_value = ticket

        await service.comment(_user(PEER), ticket.id, CommentCreate(body="oui"))

        assert ticket.status == TicketStatus.CONFIRMING.value
        assert ticket.pending_action is not None
        assert _events(service) == []

    async def test_an_approval_past_the_runs_cap_is_refused_and_writes_nothing(self) -> None:
        service = _service()
        ticket = _confirming(run_count=settings.workboard_max_runs_per_ticket)
        service.repo.get_visible.return_value = ticket

        with pytest.raises(BaseAPIException) as exc:
            await service.comment(_user(OWNER), ticket.id, CommentCreate(body="oui"))

        assert _code(exc.value) == WorkboardError.MAX_RUNS_REACHED.value
        assert ticket.status == TicketStatus.CONFIRMING.value

    async def test_handing_it_over_by_hand_still_works(self) -> None:
        """The second door stays: somebody may hand the ticket back without
        having commented since the run, and the answer is then read from their
        latest note."""
        service = _service()
        ticket = _confirming()
        service.repo.get_visible.return_value = ticket
        service.repo.owner_notes_since.return_value = [_note("oui")]

        await service.update(_user(OWNER), ticket.id, TicketUpdate(assignee="lia"))

        assert ticket.status == TicketStatus.TODO.value
        assert ticket.pending_action["approved"] is True


class TestTheModeBelongsToTheTicket:
    """2026-09-09: the person picks how LIA runs THIS ticket, and may change
    their mind for as long as the ticket lives."""

    async def test_a_new_ticket_is_born_in_the_loop(self) -> None:
        service = _service()
        await service.create(_user(OWNER), TicketCreate(title="Réserver la salle"))
        assert service.repo.create.await_args.args[0]["execution_mode"] == "react"

    async def test_the_creator_may_ask_for_the_pipeline(self) -> None:
        service = _service()
        await service.create(
            _user(OWNER), TicketCreate(title="Réserver la salle", execution_mode="pipeline")
        )
        assert service.repo.create.await_args.args[0]["execution_mode"] == "pipeline"

    async def test_the_owner_changes_it_at_any_point_of_the_tickets_life(self) -> None:
        service = _service()
        ticket = _ticket(status=TicketStatus.IN_PROGRESS.value, execution_mode="react")
        service.repo.get_visible.return_value = ticket

        await service.update(_user(OWNER), ticket.id, TicketUpdate(execution_mode="pipeline"))

        assert ticket.execution_mode == "pipeline"

    async def test_changing_it_writes_no_history_line(self) -> None:
        """It changes nothing about the work — only how the next run is driven
        — and a line per toggle would bury the ones that matter."""
        service = _service()
        ticket = _ticket(execution_mode="react")
        service.repo.get_visible.return_value = ticket

        await service.update(_user(OWNER), ticket.id, TicketUpdate(execution_mode="pipeline"))

        assert _events(service) == []

    async def test_a_holder_cannot_spend_the_owners_quota_differently(self) -> None:
        """LIA runs on the OWNER's account: the mode is theirs to choose."""
        service = _service()
        ticket = _ticket(assignee_user_id=PEER, execution_mode="react")
        service.repo.get_visible.return_value = ticket

        await service.update(_user(PEER), ticket.id, TicketUpdate(execution_mode="pipeline"))

        assert ticket.execution_mode == "react"

    async def test_an_update_that_says_nothing_leaves_it_alone(self) -> None:
        service = _service()
        ticket = _ticket(execution_mode="pipeline")
        service.repo.get_visible.return_value = ticket

        await service.update(_user(OWNER), ticket.id, TicketUpdate(priority="high"))

        assert ticket.execution_mode == "pipeline"
