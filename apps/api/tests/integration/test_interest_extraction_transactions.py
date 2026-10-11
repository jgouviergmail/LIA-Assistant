"""Real independent sessions prove the automatic writer's preparation/management fence."""

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from unittest.mock import AsyncMock, patch
from uuid import uuid4

import pytest
from sqlalchemy import delete, func, select
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession

from src.domains.interests.management_commands import create_managed_interest
from src.domains.interests.models import UserInterest
from src.domains.interests.schemas import ExtractedInterest, InterestCreate
from src.domains.interests.services.extraction_storage import (
    ObsoleteInterestExtraction,
    store_interest_extraction,
)
from src.domains.users.models import User
from tests.integration.test_application_memory_independent_transactions import (
    assert_independent_lock_control,
)

pytestmark = pytest.mark.integration


@pytest.mark.parametrize("manual_change", [False, True])
async def test_interest_embeddings_precede_user_lock_and_cannot_overwrite_manual_creation(
    async_engine: AsyncEngine, manual_change: bool
) -> None:
    owner = uuid4()
    async with AsyncSession(async_engine, expire_on_commit=False) as seed:
        seed.add(
            User(
                id=owner,
                email=f"interest-extraction-{owner}@example.test",
                full_name="Disposable",
                is_active=True,
                is_verified=True,
            )
        )
        await seed.commit()
        revision = await seed.scalar(select(User.extraction_revision).where(User.id == owner))
    assert revision is not None
    observer_connection = await async_engine.connect()
    try:
        async with AsyncSession(async_engine) as control:
            await assert_independent_lock_control(control, async_engine, owner)
        write_pid = None

        @asynccontextmanager
        async def factory() -> AsyncIterator[AsyncSession]:
            nonlocal write_pid
            async with AsyncSession(async_engine, expire_on_commit=False) as db:
                write_pid = await db.scalar(select(func.pg_backend_pid()))
                try:
                    yield db
                except BaseException:
                    await db.rollback()
                    raise

        async def embed(topic: str) -> None:
            assert topic == "Automatic topic"
            async with AsyncSession(observer_connection, expire_on_commit=False) as other:
                assert (
                    await other.scalar(
                        select(User.id).where(User.id == owner).with_for_update(nowait=True)
                    )
                    == owner
                )
                assert await other.scalar(select(func.pg_backend_pid())) != write_pid
                await other.rollback()
                if manual_change:
                    await create_managed_interest(
                        other, owner, InterestCreate(topic="Manual topic"), embedding=None
                    )
                    await other.commit()
            return None

        with (
            patch(
                "src.domains.interests.services.extraction_storage.enforce_usage_limit",
                new_callable=AsyncMock,
            ),
            patch(
                "src.domains.interests.helpers.generate_interest_embedding", side_effect=embed
            ) as provider,
        ):
            call = store_interest_extraction(
                factory,
                owner,
                revision,
                [
                    ExtractedInterest(
                        action="create",
                        topic="Automatic topic",
                        category="science",
                        confidence=0.95,
                    )
                ],
                session_id="lock-proof",
                conversation_id=None,
                run_id=None,
            )
            if manual_change:
                with pytest.raises(ObsoleteInterestExtraction):
                    await call
            else:
                assert await call == 1
        assert write_pid is not None
        assert provider.await_count == 1  # Dedup and insert reuse the same vector.
        async with AsyncSession(async_engine) as check:
            topics = list(
                (
                    await check.scalars(
                        select(UserInterest.topic).where(UserInterest.user_id == owner)
                    )
                ).all()
            )
            assert topics == ["Manual topic" if manual_change else "Automatic topic"]
    finally:
        await observer_connection.close()
        async with AsyncSession(async_engine) as cleanup:
            await cleanup.execute(delete(User).where(User.id == owner))
            await cleanup.commit()
