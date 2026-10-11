"""Manual feedback must lock the actor before dependent presence writes can form a cycle."""

from datetime import UTC, datetime
from unittest.mock import patch
from uuid import uuid4

import pytest
from sqlalchemy import delete, select
from sqlalchemy.exc import DBAPIError
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession

from src.domains.interests.models import UserInterest
from src.domains.interests.router import submit_feedback
from src.domains.interests.schemas import InterestFeedbackRequest
from src.domains.users.models import User
from tests.integration.test_application_memory_independent_transactions import (
    assert_independent_lock_control,
)

pytestmark = pytest.mark.integration


async def test_feedback_holds_user_lock_before_presence_foreign_key_write(
    async_engine: AsyncEngine,
) -> None:
    owner, identity = uuid4(), uuid4()
    async with AsyncSession(async_engine) as seed:
        seed.add(
            User(
                id=owner,
                email=f"feedback-lock-{owner}@example.test",
                full_name="Disposable",
                is_active=True,
                is_verified=True,
            )
        )
        await seed.commit()
        seed.add(
            UserInterest(
                id=identity,
                user_id=owner,
                topic="Source topic",
                category="science",
                last_mentioned_at=datetime.now(UTC),
            )
        )
        await seed.commit()
    try:
        async with AsyncSession(async_engine, expire_on_commit=False) as db:
            await assert_independent_lock_control(db, async_engine, owner)
            actor = await db.get(User, owner)
            assert actor is not None

            async def presence(*args, **kwargs):
                async with AsyncSession(async_engine) as observer:
                    with pytest.raises(DBAPIError) as refusal:
                        await observer.scalar(
                            select(User.id).where(User.id == owner).with_for_update(nowait=True)
                        )
                    assert getattr(refusal.value.orig, "sqlstate", None) == "55P03"
                    await observer.rollback()
                return "disabled"

            with patch("src.domains.habits.presence.record_presence", side_effect=presence):
                await submit_feedback(
                    identity, InterestFeedbackRequest(feedback="thumbs_up"), actor, db
                )
    finally:
        async with AsyncSession(async_engine) as cleanup:
            await cleanup.execute(delete(User).where(User.id == owner))
            await cleanup.commit()
