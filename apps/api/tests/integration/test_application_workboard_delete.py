"""Native deletion freezes the source subtree and never announces a false or stale removal."""

from unittest.mock import AsyncMock
from uuid import uuid4

import pytest
from sqlalchemy import func, select, update

from src.core.config import settings
from src.core.exceptions import (
    AuthorizationError,
    ResourceConflictError,
    ResourceNotFoundError,
    ValidationError,
)
from src.domains.agents.application.command_service import CommandRejected
from src.domains.agents.application.workboard_delete import (
    execute_workboard_delete,
    prepare_workboard_delete,
)
from src.domains.agents.application.workboard_delete_schemas import WorkboardDeleteInput
from src.domains.users.models import User
from src.domains.users.preference_cas import PreferenceWriteReceipt
from src.domains.workboard.models import WorkboardComment, WorkboardTicket
from src.domains.workboard.schemas import CommentCreate, TicketCreate
from src.domains.workboard.service import WorkboardService

pytestmark = pytest.mark.integration


async def test_deletion_names_and_removes_exact_source_subtree(
    async_session, test_user, monkeypatch
):
    monkeypatch.setattr(settings, "workboard_enabled", True)
    service = WorkboardService(async_session)
    parent = await service.create(test_user, TicketCreate(title="Exact parent"))
    child = await service.create(test_user, TicketCreate(title="Exact child", parent_id=parent.id))
    await service.comment(test_user, child.id, CommentCreate(body="Literal child comment"))
    await async_session.commit()
    draft = await prepare_workboard_delete(
        async_session, test_user.id, WorkboardDeleteInput(ticket_id=parent.id)
    )
    selected = draft.after["workboard_delete"]
    assert selected["tickets"] == 2 and selected["comments"] == 1
    assert "Exact child" in str(selected)
    assert await async_session.scalar(select(func.count(WorkboardTicket.id))) == 2
    receipt = PreferenceWriteReceipt()
    await execute_workboard_delete(async_session, test_user.id, draft, receipt)
    assert receipt.committed
    assert await async_session.scalar(select(func.count(WorkboardTicket.id))) == 0
    assert await async_session.scalar(select(func.count(WorkboardComment.id))) == 0
    assert receipt.values["workboard_delete"]["removed"] == 2


@pytest.mark.parametrize("scenario", ["changed", "new_child", "false_source"])
async def test_changed_scope_and_false_delete_are_refused(
    async_session, test_user, monkeypatch, scenario
):
    monkeypatch.setattr(settings, "workboard_enabled", True)
    service = WorkboardService(async_session)
    parent = await service.create(test_user, TicketCreate(title="Pinned parent"))
    await async_session.commit()
    draft = await prepare_workboard_delete(
        async_session, test_user.id, WorkboardDeleteInput(ticket_id=parent.id)
    )
    if scenario == "changed":
        await async_session.execute(
            update(WorkboardTicket)
            .where(WorkboardTicket.id == parent.id)
            .values(title="Changed parent")
        )
        await async_session.commit()
    elif scenario == "new_child":
        await service.create(
            test_user, TicketCreate(title="Unconfirmed child", parent_id=parent.id)
        )
        await async_session.commit()
    else:
        monkeypatch.setattr(WorkboardService, "delete", AsyncMock(return_value=1))
    receipt = PreferenceWriteReceipt()
    with pytest.raises(ValueError if scenario == "false_source" else ResourceConflictError):
        await execute_workboard_delete(async_session, test_user.id, draft, receipt)
    await async_session.rollback()
    assert not receipt.committed
    assert await async_session.scalar(select(func.count(WorkboardTicket.id))) == (
        2 if scenario == "new_child" else 1
    )


@pytest.mark.parametrize(
    "scenario", ["foreign", "holder", "disabled", "application_disabled", "expired", "tampered"]
)
async def test_deletion_authority_and_canonical_consent(
    async_session, test_user, monkeypatch, scenario
):
    from datetime import UTC, datetime, timedelta

    monkeypatch.setattr(settings, "workboard_enabled", True)
    owner = test_user
    if scenario == "holder":
        owner = User(id=uuid4(), email=f"delete-owner-{uuid4()}@example.test", is_active=True)
        async_session.add(owner)
        await async_session.flush()
    ticket = await WorkboardService(async_session).create(
        owner, TicketCreate(title="Authority target")
    )
    if scenario == "holder":
        ticket.assignee_user_id = test_user.id
    identity = ticket.id
    await async_session.commit()
    payload = WorkboardDeleteInput(ticket_id=uuid4() if scenario == "foreign" else ticket.id)
    if scenario in {"foreign", "holder"}:
        with pytest.raises(ResourceNotFoundError if scenario == "foreign" else ValidationError):
            await prepare_workboard_delete(async_session, test_user.id, payload)
        return
    draft = await prepare_workboard_delete(async_session, test_user.id, payload)
    if scenario in {"disabled", "application_disabled"}:
        monkeypatch.setattr(
            settings,
            (
                "application_tools_enabled"
                if scenario == "application_disabled"
                else "workboard_enabled"
            ),
            False,
        )
        refused = AuthorizationError
    elif scenario == "expired":
        draft = draft.model_copy(update={"expires_at": datetime.now(UTC) - timedelta(seconds=1)})
        refused = CommandRejected
    else:
        draft = draft.model_copy(update={"after": {"workboard_delete": {"tickets": 0}}})
        refused = ValueError
    receipt = PreferenceWriteReceipt()
    with pytest.raises(refused):
        await execute_workboard_delete(async_session, test_user.id, draft, receipt)
    await async_session.rollback()
    assert not receipt.committed
    assert await async_session.get(WorkboardTicket, identity, populate_existing=True) is not None


@pytest.mark.parametrize(
    "scenario", ["extra_delete", "late_disabled", "lost_ack", "cancelled_ack", "new_comment"]
)
async def test_deletion_adversarial_commit_and_scope(
    async_session, test_user, monkeypatch, scenario
):
    import asyncio

    from sqlalchemy import delete

    monkeypatch.setattr(settings, "workboard_enabled", True)
    service = WorkboardService(async_session)
    ticket = await service.create(test_user, TicketCreate(title="Pinned target"))
    other = await service.create(test_user, TicketCreate(title="Unconfirmed extra ticket"))
    other_id = other.id
    await async_session.commit()
    draft = await prepare_workboard_delete(
        async_session, test_user.id, WorkboardDeleteInput(ticket_id=ticket.id)
    )
    source_delete = WorkboardService.delete
    if scenario in {"extra_delete", "late_disabled"}:

        async def altered(service, actor, identity):
            result = await source_delete(service, actor, identity)
            if scenario == "late_disabled":
                monkeypatch.setattr(settings, "workboard_enabled", False)
            else:
                await service.db.execute(
                    delete(WorkboardTicket).where(WorkboardTicket.id == other.id)
                )
            return result

        monkeypatch.setattr(WorkboardService, "delete", altered)
        refused = AuthorizationError if scenario == "late_disabled" else ValueError
    elif scenario == "new_comment":
        await service.comment(test_user, ticket.id, CommentCreate(body="Unconfirmed new comment"))
        await async_session.commit()
        refused = ResourceConflictError
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
        refused = CommandRejected
    receipt = PreferenceWriteReceipt()
    with pytest.raises(refused) as caught:
        await execute_workboard_delete(async_session, test_user.id, draft, receipt)
    if scenario in {"lost_ack", "cancelled_ack"}:
        assert caught.value.code == "COMPLETION_UNKNOWN"
    await async_session.rollback()
    assert not receipt.committed
    assert await async_session.scalar(select(func.count(WorkboardTicket.id))) == (
        1 if scenario in {"lost_ack", "cancelled_ack"} else 2
    )
    assert await async_session.get(WorkboardTicket, other_id, populate_existing=True) is not None
