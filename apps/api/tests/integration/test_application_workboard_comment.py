"""Confirmed comments preserve the source pending-action semantics and exact text."""

from unittest.mock import AsyncMock
from uuid import uuid4

import pytest
from sqlalchemy import func, select, update

from src.core.config import settings
from src.core.exceptions import ResourceConflictError, ResourceNotFoundError
from src.domains.agents.application.command_service import CommandRejected
from src.domains.agents.application.workboard_comment import (
    execute_workboard_comment,
    prepare_workboard_comment,
)
from src.domains.agents.application.workboard_comment_schemas import WorkboardCommentInput
from src.domains.users.preference_cas import PreferenceWriteReceipt
from src.domains.workboard.models import WorkboardComment, WorkboardTicket
from src.domains.workboard.schemas import TicketCreate
from src.domains.workboard.service import WorkboardService

pytestmark = pytest.mark.integration


@pytest.mark.parametrize(
    "body,answer",
    [
        ("Literal <script>body</script>", None),
        ("Oui", "approve"),
        ("Non", "refuse"),
        ("Oui mais change le sujet", "amend"),
    ],
)
async def test_exact_comment_and_pending_answer(
    async_session, test_user, monkeypatch, body, answer
):
    monkeypatch.setattr(settings, "workboard_enabled", True)
    notice = AsyncMock(return_value=True)
    monkeypatch.setattr("src.domains.shared.proactive_sink.send_proactive_notification", notice)
    ticket = await WorkboardService(async_session).create(
        test_user, TicketCreate(title="Comment target")
    )
    if answer:
        ticket.status = "confirming"
        ticket.pending_action = {
            "draft_type": "email",
            "tool_name": "send_email_tool",
            "draft_content": {
                "to": "recipient@example.test",
                "subject": "Exact original action",
                "body": "Literal original body",
            },
        }
    await async_session.commit()
    draft = await prepare_workboard_comment(
        async_session, test_user.id, WorkboardCommentInput(ticket_id=ticket.id, body=body)
    )
    public = draft.after["workboard_comment"]
    assert public["answer"] == answer and public["body"] == body
    if answer:
        assert "Exact original action" in str(public["pending_preview"])
    assert await async_session.scalar(select(func.count(WorkboardComment.id))) == 0
    receipt = PreferenceWriteReceipt()
    await execute_workboard_comment(async_session, test_user.id, draft, receipt)
    assert receipt.committed
    posted = await async_session.get(WorkboardComment, draft.command_id)
    assert (
        posted.ticket_id == ticket.id
        and posted.body == body
        and posted.author_user_id == test_user.id
    )
    await async_session.refresh(ticket)
    assert ticket.status == ("done" if answer == "refuse" else "todo")
    if answer in {"approve", "amend"}:
        assert ticket.assignee_kind == "lia" and ticket.run_attempts == 0
        assert (ticket.pending_action or {}).get("approved", False) == (answer == "approve")
    notice.assert_not_awaited()


@pytest.mark.parametrize("scenario", ["changed", "foreign", "false_source"])
async def test_comment_refusals_roll_back_without_publishing(
    async_session, test_user, monkeypatch, scenario
):
    monkeypatch.setattr(settings, "workboard_enabled", True)
    ticket = await WorkboardService(async_session).create(
        test_user, TicketCreate(title="Stable target")
    )
    await async_session.commit()
    identity = uuid4() if scenario == "foreign" else ticket.id
    request_data = WorkboardCommentInput(ticket_id=identity, body="Exact body")
    if scenario == "foreign":
        with pytest.raises(ResourceNotFoundError):
            await prepare_workboard_comment(async_session, test_user.id, request_data)
        return
    draft = await prepare_workboard_comment(async_session, test_user.id, request_data)
    if scenario == "changed":
        await async_session.execute(
            update(WorkboardTicket).where(WorkboardTicket.id == ticket.id).values(title="Changed")
        )
        await async_session.commit()
        expected_error = ResourceConflictError
    else:
        monkeypatch.setattr(
            WorkboardService,
            "comment",
            AsyncMock(
                return_value=WorkboardComment(
                    id=draft.command_id,
                    ticket_id=ticket.id,
                    body="Exact body",
                    author_kind="user",
                    author_user_id=test_user.id,
                )
            ),
        )
        expected_error = ValueError
    receipt = PreferenceWriteReceipt()
    with pytest.raises(expected_error):
        await execute_workboard_comment(async_session, test_user.id, draft, receipt)
    await async_session.rollback()
    assert (
        not receipt.committed
        and await async_session.scalar(select(func.count(WorkboardComment.id))) == 0
    )


@pytest.mark.parametrize(
    "scenario", ["false_priority", "false_answer", "late_disabled", "lost_ack", "cancelled_ack"]
)
async def test_comment_adversarial_postconditions_and_commit(
    async_session, test_user, monkeypatch, scenario
):
    import asyncio

    monkeypatch.setattr(settings, "workboard_enabled", True)
    ticket = await WorkboardService(async_session).create(
        test_user, TicketCreate(title="Reviewed target")
    )
    ticket.status = "confirming"
    ticket.pending_action = {
        "draft_type": "email",
        "tool_name": "send_email_tool",
        "draft_content": {
            "to": "recipient@example.test",
            "subject": "Pinned pending action",
            "body": "Exact body",
        },
    }
    await async_session.commit()
    draft = await prepare_workboard_comment(
        async_session, test_user.id, WorkboardCommentInput(ticket_id=ticket.id, body="Oui")
    )
    source_comment = WorkboardService.comment
    if scenario in {"false_priority", "false_answer", "late_disabled"}:

        async def altered(service, actor, identity, data, **kwargs):
            result = await source_comment(service, actor, identity, data, **kwargs)
            if scenario == "late_disabled":
                monkeypatch.setattr(settings, "workboard_enabled", False)
            else:
                values = (
                    {"priority": "urgent"}
                    if scenario == "false_priority"
                    else {"pending_action": None}
                )
                await service.db.execute(
                    update(WorkboardTicket).where(WorkboardTicket.id == identity).values(**values)
                )
            return result

        monkeypatch.setattr(WorkboardService, "comment", altered)
    else:
        real_commit = async_session.commit

        async def unknown_commit():
            await real_commit()
            raise (
                asyncio.CancelledError()
                if scenario == "cancelled_ack"
                else OSError("Lost commit acknowledgement")
            )

        monkeypatch.setattr(async_session, "commit", unknown_commit)
    receipt = PreferenceWriteReceipt()
    if scenario == "late_disabled":
        from src.core.exceptions import AuthorizationError

        error = AuthorizationError
    else:
        error = CommandRejected if scenario in {"lost_ack", "cancelled_ack"} else ValueError
    with pytest.raises(error) as caught:
        await execute_workboard_comment(async_session, test_user.id, draft, receipt)
    if scenario in {"lost_ack", "cancelled_ack"}:
        assert caught.value.code == "COMPLETION_UNKNOWN"
    await async_session.rollback()
    assert not receipt.committed
    count = await async_session.scalar(select(func.count(WorkboardComment.id)))
    assert count == (1 if scenario in {"lost_ack", "cancelled_ack"} else 0)
