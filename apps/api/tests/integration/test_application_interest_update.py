"""Exact confirmed edits reject competing facts and prepare vectors without premature writes."""

from datetime import UTC, datetime
from unittest.mock import AsyncMock, patch

import pytest
from sqlalchemy import select, update
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.config import settings
from src.core.exceptions import (
    ResourceConflictError,
    ResourceNotFoundError,
    UsageLimitExceededError,
)
from src.domains.agents.application.command_service import CommandRejected
from src.domains.agents.application.interest_update import (
    execute_interest_update,
    prepare_interest_update,
)
from src.domains.agents.application.interest_update_schemas import InterestUpdateRequest
from src.domains.interests.models import UserInterest
from src.domains.users.models import User
from src.domains.users.preference_cas import PreferenceWriteReceipt

pytestmark = pytest.mark.integration


@pytest.mark.parametrize(
    "scenario",
    [
        "normal",
        "noop",
        "stale",
        "late_disabled",
        "quota",
        "unknown_commit",
        "foreign",
        "signals",
        "status_changed",
        "notification_arrives",
        "deleted_during_embedding",
    ],
)
async def test_exact_interest_update_uses_source_fields_and_single_approved_effect(
    async_session: AsyncSession, test_user: User, monkeypatch: pytest.MonkeyPatch, scenario: str
) -> None:
    owner = test_user.id
    row = UserInterest(
        user_id=owner,
        topic="Old topic",
        category="science",
        subject="Old subject",
        positive_signals=3,
        negative_signals=1,
        status="active",
        embedding=[0.1] * settings.interest_embedding_dimensions,
        last_mentioned_at=datetime.now(UTC),
    )
    async_session.add(row)
    await async_session.commit()
    identity = row.id
    revision = test_user.extraction_revision
    changes = {"topic": "Old topic" if scenario == "noop" else "New topic", "negative_signals": 0}
    if scenario == "noop":
        changes.pop("negative_signals")
    elif scenario == "signals":
        changes = {"negative_signals": 0}
    request = InterestUpdateRequest(interest_id=identity, changes=changes)
    if scenario == "foreign":
        from uuid import uuid4

        other_id = uuid4()
        async_session.add(
            User(
                id=other_id,
                email=f"foreign-interest-{other_id}@example.test",
                full_name="Other",
                is_active=True,
                is_verified=True,
            )
        )
        await async_session.commit()
        with pytest.raises(ResourceNotFoundError):
            await prepare_interest_update(async_session, other_id, request)
        return
    draft = await prepare_interest_update(async_session, owner, request)
    assert row.topic == "Old topic" and row.subject == "Old subject"
    assert draft.before != draft.after or scenario == "noop"
    if scenario == "status_changed":
        await async_session.execute(
            update(UserInterest).where(UserInterest.id == identity).values(status="blocked")
        )
        await async_session.commit()
    elif scenario == "notification_arrives":
        await async_session.execute(
            update(UserInterest)
            .where(UserInterest.id == identity)
            .values(last_notified_at=datetime.now(UTC))
        )
        await async_session.commit()
    elif scenario == "stale":
        await async_session.execute(
            update(UserInterest).where(UserInterest.id == identity).values(positive_signals=4)
        )
        await async_session.commit()

    async def embed(topic: str) -> None:
        assert topic == "New topic"
        if scenario == "late_disabled":
            monkeypatch.setattr(settings, "application_tools_enabled", False)
        elif scenario == "deleted_during_embedding":
            await async_session.delete(row)
            await async_session.commit()
        return None

    quota = AsyncMock(
        side_effect=(
            UsageLimitExceededError(limit_name="cycle_cost") if scenario == "quota" else None
        )
    )
    receipt = PreferenceWriteReceipt()
    with (
        patch(
            "src.domains.interests.helpers.generate_interest_embedding", side_effect=embed
        ) as provider,
        patch("src.domains.agents.application.interest_embeddings.enforce_usage_limit", quota),
    ):
        if scenario == "unknown_commit":
            with patch.object(async_session, "commit", side_effect=SQLAlchemyError("ack lost")):
                with pytest.raises(CommandRejected, match="COMPLETION_UNKNOWN"):
                    await execute_interest_update(async_session, owner, draft, receipt)
            await async_session.rollback()
        elif scenario in {"stale", "status_changed", "deleted_during_embedding"}:
            with pytest.raises(ResourceConflictError):
                await execute_interest_update(async_session, owner, draft, receipt)
            await async_session.rollback()
        elif scenario == "quota":
            with pytest.raises(UsageLimitExceededError):
                await execute_interest_update(async_session, owner, draft, receipt)
            await async_session.rollback()
        elif scenario == "late_disabled":
            from src.core.exceptions import AuthorizationError

            with pytest.raises(AuthorizationError):
                await execute_interest_update(async_session, owner, draft, receipt)
            await async_session.rollback()
        else:
            await execute_interest_update(async_session, owner, draft, receipt)
        assert provider.await_count == int(
            scenario
            in {
                "normal",
                "notification_arrives",
                "late_disabled",
                "unknown_commit",
                "deleted_during_embedding",
            }
        )
    if scenario == "deleted_during_embedding":
        assert await async_session.get(UserInterest, identity) is None
        assert not receipt.committed
        return
    actual = (
        await async_session.scalars(
            select(UserInterest)
            .where(UserInterest.id == identity)
            .execution_options(populate_existing=True)
        )
    ).one()
    assert actual.topic == (
        "New topic" if scenario in {"normal", "notification_arrives"} else "Old topic"
    )
    if scenario in {"normal", "notification_arrives"}:
        assert actual.subject is None and actual.embedding is None and actual.negative_signals == 0
        assert (
            await async_session.scalar(select(User.extraction_revision).where(User.id == owner))
            == revision + 1
        )
        assert receipt.committed
    elif scenario == "signals":
        assert actual.subject == "Old subject" and actual.embedding is not None
        assert actual.negative_signals == 0 and receipt.committed
        assert (
            await async_session.scalar(select(User.extraction_revision).where(User.id == owner))
            == revision + 1
        )
    elif scenario == "noop":
        assert receipt.no_op and receipt.committed
        assert (
            await async_session.scalar(select(User.extraction_revision).where(User.id == owner))
            == revision
        )


async def test_manual_ui_update_uses_fresh_shared_mapping_and_ignores_optional_null(
    async_session: AsyncSession, test_user: User, monkeypatch: pytest.MonkeyPatch
) -> None:
    from src.domains.interests.router import update_interest
    from src.domains.interests.schemas import InterestUpdate

    monkeypatch.setattr(settings, "application_tools_enabled", False)
    row = UserInterest(
        user_id=test_user.id,
        topic="Source topic",
        category="science",
        positive_signals=3,
        negative_signals=2,
        subject="Source grouping",
        embedding=[0.1] * settings.interest_embedding_dimensions,
        last_mentioned_at=datetime.now(UTC),
    )
    async_session.add(row)
    await async_session.commit()
    identity, revision = row.id, test_user.extraction_revision
    with patch(
        "src.domains.interests.router.generate_interest_embedding",
        new_callable=AsyncMock,
        return_value=None,
    ) as provider:
        response = await update_interest(
            identity, InterestUpdate(topic=None, negative_signals=0), test_user, async_session
        )
        assert response.topic == "Source topic" and response.negative_signals == 0
        provider.assert_not_called()
        response = await update_interest(
            identity, InterestUpdate(topic="Renamed source topic"), test_user, async_session
        )
        provider.assert_awaited_once_with("Renamed source topic")
    await async_session.refresh(row)
    assert (
        response.topic == "Renamed source topic" and row.subject is None and row.embedding is None
    )
    assert (
        await async_session.scalar(select(User.extraction_revision).where(User.id == test_user.id))
        == revision + 2
    )
