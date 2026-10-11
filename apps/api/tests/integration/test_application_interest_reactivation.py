"""Reactivation resets exactly the source state after confirmation, never an active/blocked row."""

from datetime import UTC, datetime, timedelta
from unittest.mock import patch
from uuid import uuid4

import pytest
from sqlalchemy import update
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.config import settings
from src.core.constants import INTEREST_INITIAL_NEGATIVE_SIGNALS, INTEREST_INITIAL_POSITIVE_SIGNALS
from src.core.exceptions import AuthorizationError, ResourceConflictError, ResourceNotFoundError
from src.domains.agents.application import interest_reactivation
from src.domains.agents.application.command_service import CommandRejected
from src.domains.agents.application.interest_reactivation_schemas import InterestReactivateRequest
from src.domains.interests.models import UserInterest
from src.domains.users.models import User
from src.domains.users.preference_cas import PreferenceWriteReceipt

pytestmark = pytest.mark.integration


@pytest.mark.parametrize(
    "scenario",
    [
        "dormant",
        "active",
        "blocked",
        "signals_changed",
        "delivery_changed",
        "late_disabled",
        "disabled_during_reset",
        "deleted",
        "foreign",
        "unknown_commit",
    ],
)
async def test_reactivation_uses_current_source_state_and_preserves_subject_and_embedding(
    async_session: AsyncSession,
    test_user: User,
    monkeypatch: pytest.MonkeyPatch,
    scenario: str,
) -> None:
    owner = test_user.id
    old_time = datetime.now(UTC) - timedelta(days=60)
    row = UserInterest(
        user_id=owner,
        topic="Dormant topic",
        category="science",
        status=scenario if scenario in {"active", "blocked"} else "dormant",
        positive_signals=9,
        negative_signals=7,
        subject="Source subject",
        embedding=[0.25, 0.75],
        last_mentioned_at=old_time,
        last_notified_at=old_time,
        dormant_since=old_time,
    )
    async_session.add(row)
    await async_session.commit()
    identity, revision = row.id, test_user.extraction_revision
    if scenario == "foreign":
        other = User(
            id=uuid4(),
            email=f"reactivate-other-{uuid4()}@example.test",
            full_name="Other",
            is_active=True,
            is_verified=True,
        )
        async_session.add(other)
        await async_session.commit()
        with pytest.raises(ResourceNotFoundError):
            await interest_reactivation.prepare_interest_reactivation(
                async_session, other.id, InterestReactivateRequest(interest_id=identity)
            )
        return
    if scenario in {"active", "blocked"}:
        with pytest.raises(ResourceConflictError):
            await interest_reactivation.prepare_interest_reactivation(
                async_session, owner, InterestReactivateRequest(interest_id=identity)
            )
        return
    draft = await interest_reactivation.prepare_interest_reactivation(
        async_session, owner, InterestReactivateRequest(interest_id=identity)
    )
    assert row.status == "dormant" and row.positive_signals == 9
    if scenario in {"signals_changed", "delivery_changed"}:
        await async_session.execute(
            update(UserInterest)
            .where(UserInterest.id == identity)
            .values(
                **(
                    {"positive_signals": 10}
                    if scenario == "signals_changed"
                    else {"last_notified_at": datetime.now(UTC)}
                )
            )
        )
        await async_session.commit()
    elif scenario == "late_disabled":
        monkeypatch.setattr(settings, "application_tools_enabled", False)
    elif scenario == "deleted":
        await async_session.delete(row)
        await async_session.commit()
    elif scenario == "disabled_during_reset":
        source = interest_reactivation.reactivate_managed_interest

        async def reset(*args, **kwargs):
            result = await source(*args, **kwargs)
            monkeypatch.setattr(settings, "application_tools_enabled", False)
            return result

        monkeypatch.setattr(interest_reactivation, "reactivate_managed_interest", reset)
    receipt = PreferenceWriteReceipt()
    if scenario in {"signals_changed", "delivery_changed", "deleted"}:
        with pytest.raises(ResourceConflictError):
            await interest_reactivation.execute_interest_reactivation(
                async_session, owner, draft, receipt
            )
        await async_session.rollback()
        return
    if scenario in {"late_disabled", "disabled_during_reset"}:
        with pytest.raises(AuthorizationError):
            await interest_reactivation.execute_interest_reactivation(
                async_session, owner, draft, receipt
            )
        await async_session.rollback()
        await async_session.refresh(row)
        await async_session.refresh(test_user)
        assert row.status == "dormant" and row.positive_signals == 9
        assert test_user.extraction_revision == revision
        return
    if scenario == "unknown_commit":
        with patch.object(async_session, "commit", side_effect=SQLAlchemyError("ack lost")):
            with pytest.raises(CommandRejected, match="COMPLETION_UNKNOWN"):
                await interest_reactivation.execute_interest_reactivation(
                    async_session, owner, draft, receipt
                )
        await async_session.rollback()
        assert not receipt.committed
        return
    observed_before = datetime.now(UTC)
    await interest_reactivation.execute_interest_reactivation(async_session, owner, draft, receipt)
    await async_session.refresh(row)
    await async_session.refresh(test_user)
    assert receipt.committed and row.status == "active"
    assert (row.positive_signals, row.negative_signals) == (
        INTEREST_INITIAL_POSITIVE_SIGNALS,
        INTEREST_INITIAL_NEGATIVE_SIGNALS,
    )
    assert (
        row.last_mentioned_at >= observed_before
        and row.last_notified_at is None
        and row.dormant_since is None
    )
    assert (
        row.topic == "Dormant topic"
        and row.subject == "Source subject"
        and row.embedding == [0.25, 0.75]
    )
    assert test_user.extraction_revision == revision + 1
