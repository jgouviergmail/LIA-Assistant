"""Native update previews are source predictions; confirmation verifies the actual persisted result."""

from unittest.mock import AsyncMock

import pytest
from sqlalchemy import func, select, update

from src.core.config import settings
from src.core.exceptions import AuthorizationError, ResourceConflictError
from src.domains.agents.application.command_service import CommandRejected
from src.domains.agents.application.workboard_update import (
    execute_workboard_update,
    prepare_workboard_update,
)
from src.domains.agents.application.workboard_update_schemas import WorkboardUpdateInput
from src.domains.users.preference_cas import PreferenceWriteReceipt
from src.domains.workboard.models import WorkboardTicket, WorkboardTicketEvent
from src.domains.workboard.schemas import CommentCreate, TicketCreate
from src.domains.workboard.service import WorkboardService

pytestmark = pytest.mark.integration


@pytest.mark.parametrize("scenario", ["fields", "clear_dates", "move", "run_now"])
async def test_update_prepares_without_persisting_and_executes_source(
    async_session, test_user, monkeypatch, scenario
):
    from datetime import UTC, datetime, timedelta

    monkeypatch.setattr(settings, "workboard_enabled", True)
    actor_id = test_user.id
    service = WorkboardService(async_session)
    ticket = await service.create(
        test_user,
        TicketCreate(
            title="Source target",
            start_at=datetime.now(UTC) + timedelta(days=1),
            assignee="lia" if scenario == "run_now" else "me",
        ),
    )
    identity = ticket.id
    await async_session.commit()
    fields = {
        "title": "Confirmed new title",
        "priority": "high",
        "follow": True,
        "execution_mode": "pipeline",
    }
    if scenario == "clear_dates":
        fields = {"clear_start_at": True}
    elif scenario == "move":
        fields = {"move": {"status": "done", "position": 0}}
    elif scenario == "run_now":
        fields = {"run_now": True}
    payload = WorkboardUpdateInput.model_validate({"ticket_id": str(identity), **fields})
    draft = await prepare_workboard_update(async_session, actor_id, payload)
    await async_session.commit()
    actual = await async_session.get(WorkboardTicket, identity, populate_existing=True)
    assert actual.title == "Source target" and actual.priority == "medium"
    assert await async_session.scalar(select(func.count(WorkboardTicketEvent.id))) == 1
    receipt = PreferenceWriteReceipt()
    await execute_workboard_update(async_session, actor_id, draft, receipt)
    assert receipt.committed
    actual = await async_session.get(WorkboardTicket, identity, populate_existing=True)
    if scenario == "fields":
        assert actual.title == "Confirmed new title" and actual.priority == "high"
        assert actual.follow_owner and actual.execution_mode == "pipeline"
    elif scenario in {"clear_dates", "run_now"}:
        assert actual.start_at is None
    else:
        assert actual.status == "done" and actual.position == 0


@pytest.mark.parametrize(
    "scenario",
    [
        "stale",
        "application_disabled",
        "late_disabled",
        "false_source",
        "wrong_field",
        "lost_ack",
        "cancelled_ack",
    ],
)
async def test_update_refusals_and_ambiguous_commit(
    async_session, test_user, monkeypatch, scenario
):
    import asyncio

    monkeypatch.setattr(settings, "workboard_enabled", True)
    actor_id = test_user.id
    ticket = await WorkboardService(async_session).create(
        test_user, TicketCreate(title="Pinned update target")
    )
    identity = ticket.id
    await async_session.commit()
    draft = await prepare_workboard_update(
        async_session, actor_id, WorkboardUpdateInput(ticket_id=identity, title="Approved title")
    )
    source_update = WorkboardService.update
    if scenario == "stale":
        await async_session.execute(
            update(WorkboardTicket).where(WorkboardTicket.id == identity).values(priority="high")
        )
        await async_session.commit()
        refused = ResourceConflictError
    elif scenario == "application_disabled":
        monkeypatch.setattr(settings, "application_tools_enabled", False)
        refused = AuthorizationError
    elif scenario == "false_source":
        monkeypatch.setattr(WorkboardService, "update", AsyncMock(return_value=ticket))
        refused = ValueError
    elif scenario in {"late_disabled", "wrong_field"}:

        async def altered(service, actor, ticket_id, data):
            result = await source_update(service, actor, ticket_id, data)
            if scenario == "late_disabled":
                monkeypatch.setattr(settings, "workboard_enabled", False)
            else:
                await service.db.execute(
                    update(WorkboardTicket)
                    .where(WorkboardTicket.id == identity)
                    .values(priority="urgent")
                )
            return result

        monkeypatch.setattr(WorkboardService, "update", altered)
        refused = AuthorizationError if scenario == "late_disabled" else ValueError
    else:
        commit = async_session.commit

        async def ambiguous():
            await commit()
            raise (
                asyncio.CancelledError()
                if scenario == "cancelled_ack"
                else OSError("Lost commit acknowledgement")
            )

        monkeypatch.setattr(async_session, "commit", ambiguous)
        refused = CommandRejected
    receipt = PreferenceWriteReceipt()
    with pytest.raises(refused) as caught:
        await execute_workboard_update(async_session, actor_id, draft, receipt)
    if scenario in {"lost_ack", "cancelled_ack"}:
        assert caught.value.code == "COMPLETION_UNKNOWN"
    await async_session.rollback()
    assert not receipt.committed
    actual = await async_session.get(WorkboardTicket, identity, populate_existing=True)
    assert actual.title == (
        "Approved title" if scenario in {"lost_ack", "cancelled_ack"} else "Pinned update target"
    )
    assert actual.priority == ("high" if scenario == "stale" else "medium")


@pytest.mark.parametrize(
    "answer,expected",
    [
        ("Oui", "approve"),
        ("Non", "refuse"),
        ("Oui mais modifie le sujet", "amend"),
        (None, "discard"),
    ],
)
async def test_update_exposes_source_pending_action_consequences(
    async_session, test_user, monkeypatch, answer, expected
):
    from datetime import UTC, datetime, timedelta

    monkeypatch.setattr(settings, "workboard_enabled", True)
    actor_id = test_user.id
    service = WorkboardService(async_session)
    ticket = await service.create(test_user, TicketCreate(title="Waiting source ticket"))
    identity = ticket.id
    if answer is not None:
        await service.comment(test_user, identity, CommentCreate(body=answer))
    ticket.last_run_at = datetime.now(UTC) - timedelta(minutes=5)
    ticket.status = "confirming"
    ticket.pending_action = {
        "draft_type": "email",
        "tool_name": "send_email_tool",
        "draft_content": {
            "to": "recipient@example.test",
            "subject": "Exact pending subject",
            "body": "Original body",
        },
    }
    await async_session.commit()
    changes = {"status": "done"} if expected == "discard" else {"assignee": "lia"}
    draft = await prepare_workboard_update(
        async_session,
        actor_id,
        WorkboardUpdateInput.model_validate({"ticket_id": identity, **changes}),
    )
    public = draft.after["workboard_update"]
    assert "Exact pending subject" in str(public["pending_preview"])
    assert public["answer"] == (None if expected == "discard" else expected)
    assert public["pending_action_approved"] == (expected == "approve")
    assert public["pending_action_discarded"] == (expected != "approve")
    receipt = PreferenceWriteReceipt()
    await execute_workboard_update(async_session, actor_id, draft, receipt)
    assert receipt.committed
    actual = await async_session.get(WorkboardTicket, identity, populate_existing=True)
    assert bool((actual.pending_action or {}).get("approved")) == (expected == "approve")
    assert actual.status == ("done" if expected in {"refuse", "discard"} else "todo")
