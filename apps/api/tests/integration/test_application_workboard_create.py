"""A workboard creation proposes first and persists only the approved canonical request."""

from datetime import UTC, datetime, timedelta
from unittest.mock import AsyncMock

import pytest
from sqlalchemy import func, select, update
from sqlalchemy.exc import OperationalError

from src.core.config import settings
from src.core.exceptions import AuthorizationError, ResourceConflictError
from src.domains.agents.application.command_service import CommandRejected
from src.domains.agents.application.workboard_create import (
    execute_workboard_creation,
    prepare_workboard_creation,
)
from src.domains.agents.application.workboard_create_schemas import WorkboardCreateInput
from src.domains.users.preference_cas import PreferenceWriteReceipt
from src.domains.workboard.models import WorkboardTicket

pytestmark = pytest.mark.integration


@pytest.mark.parametrize(
    "scenario",
    [
        "created",
        "lia",
        "native_off",
        "workboard_off",
        "expired",
        "changed_cap",
        "lost_ack",
        "late_off",
        "false_field",
        "committed_lost_ack",
    ],
)
async def test_workboard_creation_exact_scope(async_session, test_user, monkeypatch, scenario):
    monkeypatch.setattr(settings, "workboard_enabled", True)
    owner = test_user.id
    draft = await prepare_workboard_creation(
        async_session,
        owner,
        WorkboardCreateInput(
            title="  Exact title  ",
            description="My literal brief",
            assignee="lia" if scenario == "lia" else "me",
        ),
    )
    assert await async_session.scalar(select(func.count(WorkboardTicket.id))) == 0
    if scenario == "native_off":
        monkeypatch.setattr(settings, "application_tools_enabled", False)
    if scenario == "workboard_off":
        monkeypatch.setattr(settings, "workboard_enabled", False)
    if scenario == "expired":
        draft = draft.model_copy(update={"expires_at": datetime.now(UTC) - timedelta(seconds=1)})
    if scenario == "changed_cap":
        monkeypatch.setattr(
            settings, "workboard_max_tickets_per_user", settings.workboard_max_tickets_per_user + 1
        )
    if scenario == "lost_ack":
        monkeypatch.setattr(
            async_session,
            "commit",
            AsyncMock(side_effect=OperationalError("commit", {}, RuntimeError("lost ack"))),
        )
    if scenario == "committed_lost_ack":
        source_commit = async_session.commit

        async def lost_commit_reply():
            await source_commit()
            raise OperationalError("commit", {}, RuntimeError("lost ack"))

        monkeypatch.setattr(async_session, "commit", lost_commit_reply)
    if scenario in {"late_off", "false_field"}:
        from src.domains.workboard.service import WorkboardService

        source_create = WorkboardService.create

        async def changed_source(service, *args, **kwargs):
            result = await source_create(service, *args, **kwargs)
            if scenario == "late_off":
                monkeypatch.setattr(settings, "application_tools_enabled", False)
            else:
                await service.db.execute(
                    update(WorkboardTicket)
                    .where(WorkboardTicket.id == result.id)
                    .values(priority="urgent")
                    .execution_options(synchronize_session=False)
                )
            return result

        monkeypatch.setattr(WorkboardService, "create", changed_source)
    receipt = PreferenceWriteReceipt()
    if scenario in {"created", "lia"}:
        await execute_workboard_creation(async_session, owner, draft, receipt)
        assert receipt.committed
        row = await async_session.scalar(
            select(WorkboardTicket).where(WorkboardTicket.owner_user_id == owner)
        )
        assert row.title == "Exact title" and row.description == "My literal brief"
        assert row.assignee_kind == ("lia" if scenario == "lia" else "human")
        assert receipt.values["workboard_create"]["ticket_id"] == str(row.id)
        return
    with pytest.raises((CommandRejected, AuthorizationError, ResourceConflictError, ValueError)):
        await execute_workboard_creation(async_session, owner, draft, receipt)
    assert not receipt.committed
    await async_session.rollback()
    assert await async_session.scalar(select(func.count(WorkboardTicket.id))) == (
        1 if scenario == "committed_lost_ack" else 0
    )
