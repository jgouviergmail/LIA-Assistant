"""Real source transitions remain owned, exact and revocable until commit."""

from datetime import UTC, datetime, timedelta
from types import SimpleNamespace
from unittest.mock import patch
from uuid import uuid4

import pytest
from sqlalchemy import update
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.config import settings
from src.core.exceptions import AuthorizationError, ResourceConflictError, ResourceNotFoundError
from src.domains.agents.application import open_loop_actions
from src.domains.agents.application.command_service import CommandRejected
from src.domains.agents.application.open_loop_action_schemas import (
    OpenLoopCloseRequest,
    OpenLoopUpdateRequest,
)
from src.domains.open_loops.models import OpenLoop
from src.domains.users.models import User
from src.domains.users.preference_cas import PreferenceWriteReceipt

pytestmark = pytest.mark.integration


@pytest.mark.parametrize("operation", ["update", "done", "dismissed"])
@pytest.mark.parametrize(
    "scenario", ["ok", "foreign", "stale", "nudge", "closed", "source_off", "late_off", "unknown"]
)
async def test_confirmed_commitment_changes_use_source_rules_and_fresh_authority(
    async_session: AsyncSession,
    test_user: User,
    monkeypatch: pytest.MonkeyPatch,
    operation: str,
    scenario: str,
) -> None:
    monkeypatch.setattr(settings, "open_loops_enabled", True)
    owner = test_user.id
    row = OpenLoop(
        user_id=owner,
        subject="Original promise",
        counterparty="Alex",
        direction="user_owes",
        due_hint=datetime.now(UTC) + timedelta(days=2),
        source_ref="private-conversation",
    )
    async_session.add(row)
    await async_session.commit()
    identity = row.id
    request = (
        OpenLoopUpdateRequest.model_validate(
            {
                "loop_id": str(identity),
                "changes": {"subject": " Corrected promise ", "clear_due_hint": True},
            }
        )
        if operation == "update"
        else OpenLoopCloseRequest(loop_id=identity, action=operation)
    )
    if scenario == "foreign":
        other = User(
            id=uuid4(),
            email=f"loop-other-{uuid4()}@example.test",
            full_name="Other",
            is_active=True,
            is_verified=True,
        )
        async_session.add(other)
        await async_session.commit()
        with pytest.raises(ResourceNotFoundError):
            await open_loop_actions.prepare_open_loop_action(async_session, other.id, request)
        return
    draft = await open_loop_actions.prepare_open_loop_action(async_session, owner, request)
    assert row.subject == "Original promise" and row.status == "open"
    assert "private-conversation" not in str(draft.model_dump())
    if scenario in {"stale", "nudge", "closed"}:
        change = (
            {"subject": "Different promise"}
            if scenario == "stale"
            else (
                {"nudge_count": 4, "updated_at": datetime.now(UTC)}
                if scenario == "nudge"
                else {"status": "closed"}
            )
        )
        await async_session.execute(
            update(OpenLoop).where(OpenLoop.id == identity).values(**change)
        )
        await async_session.commit()
    if scenario == "source_off":
        monkeypatch.setattr(settings, "open_loops_enabled", False)
    if scenario == "late_off":
        source = open_loop_actions.apply_open_loop_change

        async def withdraw(*args, **kwargs):
            result = await source(*args, **kwargs)
            monkeypatch.setattr(settings, "application_tools_enabled", False)
            return result

        monkeypatch.setattr(open_loop_actions, "apply_open_loop_change", withdraw)
    receipt = PreferenceWriteReceipt()
    if scenario in {"stale", "closed", "source_off", "late_off"}:
        error = ResourceConflictError if scenario in {"stale", "closed"} else AuthorizationError
        with pytest.raises(error):
            await open_loop_actions.execute_open_loop_action(async_session, owner, draft, receipt)
        await async_session.rollback()
        await async_session.refresh(row)
        assert not receipt.committed
        if scenario == "late_off":
            assert row.subject == "Original promise" and row.status == "open"
        return
    if scenario == "unknown":
        with patch.object(async_session, "commit", side_effect=SQLAlchemyError("ack lost")):
            with pytest.raises(CommandRejected, match="COMPLETION_UNKNOWN"):
                await open_loop_actions.execute_open_loop_action(
                    async_session, owner, draft, receipt
                )
        await async_session.rollback()
        assert not receipt.committed
        return
    await open_loop_actions.execute_open_loop_action(async_session, owner, draft, receipt)
    await async_session.refresh(row)
    assert receipt.committed
    assert row.source_ref == "private-conversation" and row.counterparty == "Alex"
    if operation == "update":
        assert row.subject == "Corrected promise" and row.due_hint is None and row.status == "open"
    else:
        assert row.status == "closed" and row.closed_reason == (
            "api" if operation == "done" else "dismissed"
        )
    if scenario == "nudge":
        assert row.nudge_count == 4


@pytest.mark.parametrize(
    "scenario", ["deadline", "no_op", "expired_after_write", "rolled_back_closure"]
)
async def test_commitment_clock_noop_and_closure_metric_follow_actual_commit(
    async_session: AsyncSession,
    test_user: User,
    monkeypatch: pytest.MonkeyPatch,
    scenario: str,
) -> None:
    monkeypatch.setattr(settings, "open_loops_enabled", True)
    owner = test_user.id
    row = OpenLoop(user_id=owner, subject="Source wording", direction="user_owes")
    async_session.add(row)
    await async_session.commit()
    original_clock = row.updated_at
    request = (
        OpenLoopCloseRequest(loop_id=row.id)
        if scenario == "rolled_back_closure"
        else OpenLoopUpdateRequest.model_validate(
            {
                "loop_id": str(row.id),
                "changes": (
                    {"subject": "Source wording"}
                    if scenario == "no_op"
                    else {"due_hint": "2026-12-20T10:00:00+02:00"}
                ),
            }
        )
    )
    draft = await open_loop_actions.prepare_open_loop_action(async_session, owner, request)
    if scenario in {"expired_after_write", "rolled_back_closure"}:
        source = open_loop_actions.apply_open_loop_change

        async def withdraw(*args, **kwargs):
            await source(*args, **kwargs)
            if scenario == "rolled_back_closure":
                monkeypatch.setattr(settings, "open_loops_enabled", False)
            else:
                monkeypatch.setattr(
                    open_loop_actions,
                    "datetime",
                    SimpleNamespace(now=lambda zone: draft.expires_at),
                )

        monkeypatch.setattr(open_loop_actions, "apply_open_loop_change", withdraw)
    receipt = PreferenceWriteReceipt()
    with patch(
        "src.infrastructure.observability.metrics_registry.track_open_loop_closure"
    ) as counter:
        if scenario in {"expired_after_write", "rolled_back_closure"}:
            error = AuthorizationError if scenario == "rolled_back_closure" else CommandRejected
            with pytest.raises(error):
                await open_loop_actions.execute_open_loop_action(
                    async_session, owner, draft, receipt
                )
            await async_session.rollback()
            assert not receipt.committed
        else:
            await open_loop_actions.execute_open_loop_action(async_session, owner, draft, receipt)
            assert receipt.committed and receipt.no_op is (scenario == "no_op")
        counter.assert_not_called()
    await async_session.refresh(row)
    if scenario == "deadline":
        assert row.due_hint == datetime(2026, 12, 20, 8, tzinfo=UTC)
    else:
        assert row.updated_at == original_clock and row.status == "open" and row.due_hint is None
