"""Health erasure approves complete owned source scope rather than a displayed page."""

from datetime import UTC, datetime, timedelta
from unittest.mock import AsyncMock
from uuid import uuid4

import pytest
from sqlalchemy import func, select, update

from src.core.config import settings
from src.core.exceptions import AuthorizationError, ResourceConflictError
from src.domains.agents.application.command_service import CommandRejected
from src.domains.agents.application.health_removal import (
    execute_health_removal,
    prepare_health_removal,
)
from src.domains.agents.application.health_removal_schemas import HealthRemovalRequest
from src.domains.health_metrics.models import HealthSample
from src.domains.users.models import User
from src.domains.users.preference_cas import PreferenceWriteReceipt

pytestmark = pytest.mark.integration


@pytest.mark.parametrize("committed", [False, True])
async def test_sample_erasure_lost_ack_is_unknown_even_when_rows_are_gone(
    async_session, test_user, monkeypatch, committed
):
    from sqlalchemy.exc import OperationalError

    monkeypatch.setattr(settings, "health_metrics_enabled", True)
    owner = test_user.id
    start = datetime.now(UTC)
    async_session.add(
        HealthSample(
            user_id=owner,
            kind="steps",
            date_start=start,
            date_end=start + timedelta(minutes=1),
            value=1,
            source="watch",
        )
    )
    await async_session.commit()
    draft = await prepare_health_removal(async_session, owner, HealthRemovalRequest(kind=None))
    original = async_session.commit

    async def unknown():
        if committed:
            await original()
        raise OperationalError("COMMIT", {}, RuntimeError("lost acknowledgement"))

    monkeypatch.setattr(async_session, "commit", unknown)
    receipt = PreferenceWriteReceipt()
    with pytest.raises(CommandRejected) as refused:
        await execute_health_removal(async_session, owner, draft, receipt)
    assert refused.value.code == "COMPLETION_UNKNOWN" and not receipt.committed
    await async_session.rollback()
    remaining = await async_session.scalar(
        select(func.count()).select_from(HealthSample).where(HealthSample.user_id == owner)
    )
    assert remaining == (0 if committed else 1)


@pytest.mark.parametrize(
    "scenario",
    [
        "all",
        "steps",
        "empty",
        "changed",
        "new_row",
        "expired",
        "withdrawn",
        "late_withdrawal",
        "missing_effect",
    ],
)
async def test_erasure_complete_scope_and_conditional_source_effect(
    async_session, test_user, monkeypatch, scenario
):
    monkeypatch.setattr(settings, "health_metrics_enabled", True)
    owner = test_user.id
    foreign = User(id=uuid4(), email=f"health-erasure-{uuid4()}@example.test", is_active=True)
    async_session.add(foreign)
    await async_session.flush()
    start = datetime.now(UTC) - timedelta(days=1)
    rows = [
        HealthSample(
            user_id=owner,
            kind="steps",
            date_start=start + timedelta(seconds=i),
            date_end=start + timedelta(seconds=i + 1),
            value=i,
            source="watch",
        )
        for i in range(203)
    ]
    heart = HealthSample(
        user_id=owner,
        kind="heart_rate",
        date_start=start,
        date_end=start + timedelta(minutes=1),
        value=80,
        source="watch",
    )
    other = HealthSample(
        user_id=foreign.id,
        kind="steps",
        date_start=start,
        date_end=start + timedelta(minutes=1),
        value=99999,
        source="private",
    )
    async_session.add(other)
    if scenario != "empty":
        async_session.add_all([*rows, heart])
    await async_session.commit()
    request = HealthRemovalRequest(kind="steps" if scenario == "steps" else None)
    draft = await prepare_health_removal(async_session, owner, request)
    assert "99999" not in str(draft.model_dump()) and "digest" not in str(draft.before)
    if scenario == "changed":
        await async_session.execute(
            update(HealthSample)
            .where(HealthSample.id == rows[101].id)
            .values(value=777, updated_at=rows[101].updated_at)
        )
        await async_session.commit()
    if scenario == "new_row":
        async_session.add(
            HealthSample(
                user_id=owner,
                kind="steps",
                date_start=start + timedelta(days=1),
                date_end=start + timedelta(days=1, minutes=1),
                value=1,
                source="watch",
            )
        )
        await async_session.commit()
    if scenario == "expired":
        draft = draft.model_copy(update={"expires_at": datetime.now(UTC) - timedelta(seconds=1)})
    if scenario == "withdrawn":
        monkeypatch.setattr(settings, "application_tools_enabled", False)
    if scenario == "missing_effect":
        monkeypatch.setattr(
            "src.domains.health_metrics.service.HealthMetricsService.delete_all",
            AsyncMock(return_value=204),
        )
    if scenario == "late_withdrawal":
        from src.domains.health_metrics.service import HealthMetricsService

        original = HealthMetricsService.delete_all

        async def withdrawn(service, actor_id):
            count = await original(service, actor_id)
            monkeypatch.setattr(settings, "application_tools_enabled", False)
            return count

        monkeypatch.setattr(HealthMetricsService, "delete_all", withdrawn)
    receipt = PreferenceWriteReceipt()
    errors = {
        "changed": ResourceConflictError,
        "new_row": ResourceConflictError,
        "expired": CommandRejected,
        "withdrawn": AuthorizationError,
        "late_withdrawal": AuthorizationError,
        "missing_effect": ValueError,
    }
    if scenario in errors:
        with pytest.raises(errors[scenario]):
            await execute_health_removal(async_session, owner, draft, receipt)
        assert not receipt.committed
        await async_session.rollback()
        if scenario == "late_withdrawal":
            assert (
                await async_session.scalar(
                    select(func.count())
                    .select_from(HealthSample)
                    .where(HealthSample.user_id == owner)
                )
                == 204
            )
        return
    await execute_health_removal(async_session, owner, draft, receipt)
    assert receipt.committed
    own = await async_session.scalar(
        select(func.count()).select_from(HealthSample).where(HealthSample.user_id == owner)
    )
    assert own == (1 if scenario == "steps" else 0)
    assert (
        await async_session.scalar(select(HealthSample.id).where(HealthSample.id == other.id))
        is not None
    )
    assert receipt.values["health_samples_to_delete"]["affected_rows"] == (
        0 if scenario == "empty" else 203 if scenario == "steps" else 204
    )
