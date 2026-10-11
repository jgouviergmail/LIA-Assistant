"""Distinct PostgreSQL sessions prove that approved provider work holds no user write lock."""

from datetime import UTC, datetime
from unittest.mock import AsyncMock, patch
from uuid import uuid4

import pytest
from sqlalchemy import delete, func, select
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession

from src.core.config import settings
from src.domains.agents.application.interest_create_schemas import InterestCreateConfiguration
from src.domains.agents.application.interest_creation import (
    execute_interest_creation,
    prepare_interest_creation,
)
from src.domains.agents.application.interest_update import (
    execute_interest_update,
    prepare_interest_update,
)
from src.domains.agents.application.interest_update_schemas import InterestUpdateRequest
from src.domains.interests.models import UserInterest
from src.domains.users.models import User
from src.domains.users.preference_cas import PreferenceWriteReceipt
from tests.integration.test_application_memory_independent_transactions import (
    assert_independent_lock_control,
)

pytestmark = pytest.mark.integration


@pytest.mark.parametrize("operation", ["create", "update"])
async def test_interest_embedding_runs_before_real_user_row_lock(
    async_engine: AsyncEngine, monkeypatch: pytest.MonkeyPatch, operation: str
) -> None:
    monkeypatch.setattr(settings, "application_tools_enabled", True)
    owner = uuid4()
    identity = uuid4()
    async with AsyncSession(async_engine) as seed:
        seed.add(
            User(
                id=owner,
                email=f"interest-lock-{owner}@example.test",
                full_name="Disposable interest actor",
                is_active=True,
                is_verified=True,
            )
        )
        await seed.commit()
        if operation == "update":
            seed.add(
                UserInterest(
                    id=identity,
                    user_id=owner,
                    topic="Former topic",
                    category="science",
                    last_mentioned_at=datetime.now(UTC),
                )
            )
            await seed.commit()
    try:
        async with AsyncSession(async_engine, expire_on_commit=False) as db:
            await assert_independent_lock_control(db, async_engine, owner)
            parent_pid = await db.scalar(select(func.pg_backend_pid()))
            if operation == "create":
                draft = await prepare_interest_creation(
                    db,
                    owner,
                    InterestCreateConfiguration(topic="Explicit topic", category="science"),
                )
                identity = draft.command_id
            else:
                draft = await prepare_interest_update(
                    db,
                    owner,
                    InterestUpdateRequest(
                        interest_id=identity, changes={"topic": "Explicit topic"}
                    ),
                )

            async def provider(text: str) -> None:
                assert text == "Explicit topic"
                async with AsyncSession(async_engine) as observer:
                    assert await observer.scalar(select(func.pg_backend_pid())) != parent_pid
                    assert (
                        await observer.scalar(
                            select(User.id).where(User.id == owner).with_for_update(nowait=True)
                        )
                        == owner
                    )
                    await observer.rollback()
                return None

            quota = AsyncMock()
            with (
                patch(
                    "src.domains.interests.helpers.generate_interest_embedding",
                    side_effect=provider,
                ),
                patch(
                    "src.domains.agents.application.interest_embeddings.enforce_usage_limit", quota
                ),
            ):
                receipt = PreferenceWriteReceipt()
                if operation == "create":
                    await execute_interest_creation(db, owner, draft, receipt)
                else:
                    await execute_interest_update(db, owner, draft, receipt)
            assert receipt.committed
            quota.assert_awaited_once_with(owner, layer="application_interest")
            assert (
                await db.scalar(select(UserInterest.id).where(UserInterest.id == identity))
                == identity
            )
    finally:
        async with AsyncSession(async_engine) as cleanup:
            await cleanup.execute(delete(User).where(User.id == owner))
            await cleanup.commit()
