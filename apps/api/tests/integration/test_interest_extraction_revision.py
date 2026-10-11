"""A delayed automatic extraction cannot restore facts changed by explicit management."""

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from unittest.mock import AsyncMock, patch

import pytest
from langchain_core.messages import HumanMessage
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from src.domains.interests.models import InterestCategory, UserInterest
from src.domains.interests.schemas import ExtractedInterest
from src.domains.interests.services import extraction_service
from src.domains.users.models import User
from tests.helpers.runtime_context import installed_runtime_context

pytestmark = pytest.mark.integration


@pytest.mark.parametrize(
    "scenario",
    [
        "current",
        "old_run",
        "changed_during_model",
        "changed_during_embedding",
        "actor_off",
        "missing_revision",
        "foreign_runtime",
        "quota",
        "late_capability_off",
    ],
)
async def test_background_interest_writes_honor_the_durable_management_revision(
    async_session: AsyncSession, test_user: User, scenario: str
) -> None:
    owner = test_user.id
    test_user.interests_enabled = False  # This is a delivery setting, not a learning consent.
    revision = test_user.extraction_revision
    await async_session.commit()
    if scenario == "old_run":
        test_user.extraction_revision += 1
        await async_session.commit()
    elif scenario == "actor_off":
        test_user.is_active = False
        await async_session.commit()

    @asynccontextmanager
    async def session() -> AsyncIterator[AsyncSession]:
        try:
            yield async_session
            await async_session.commit()
        except BaseException:
            await async_session.rollback()
            raise

    async def analyze(**kwargs):
        if scenario == "changed_during_model":
            await async_session.execute(
                update(User).where(User.id == owner).values(extraction_revision=revision + 1)
            )
            await async_session.commit()
        return extraction_service.InterestAnalysisResult(
            analyzed=True,
            extracted_interests=[
                ExtractedInterest(
                    action="create",
                    topic="Delayed topic",
                    category=InterestCategory.SCIENCE,
                    confidence=0.95,
                )
            ],
            llm_input_tokens=11,
            llm_output_tokens=7,
        )

    model = AsyncMock(side_effect=analyze)
    tokens = AsyncMock()

    async def embed(topic: str) -> None:
        if scenario == "changed_during_embedding":
            await async_session.execute(
                update(User).where(User.id == owner).values(extraction_revision=revision + 1)
            )
            await async_session.commit()
        return None

    from uuid import uuid4

    quota = AsyncMock(side_effect=RuntimeError("quota exhausted") if scenario == "quota" else None)
    with (
        installed_runtime_context(
            user_id=uuid4() if scenario == "foreign_runtime" else owner,
            extraction_revision=None if scenario == "missing_revision" else revision,
        ),
        patch("src.domains.interests.services.extraction_service.get_db_context", session),
        patch("src.domains.interests.services.extraction_service._analyze_interests_core", model),
        patch("src.domains.interests.services.extraction_service._persist_interest_tokens", tokens),
        patch("src.domains.interests.services.extraction_storage.enforce_usage_limit", quota),
        patch(
            "src.domains.interests.services.extraction_storage.is_capability_enabled",
            new_callable=AsyncMock,
            side_effect=[True, True, False] if scenario == "late_capability_off" else None,
            return_value=True,
        ),
        patch(
            "src.domains.interests.helpers.generate_interest_embedding",
            side_effect=embed,
        ),
    ):
        count = await extraction_service.extract_interests_background(
            str(owner), [HumanMessage(content="A topic to learn")], "revision-proof"
        )
    rows = list(
        (
            await async_session.scalars(select(UserInterest).where(UserInterest.user_id == owner))
        ).all()
    )
    assert count == len(rows) == int(scenario == "current")
    assert model.await_count == int(
        scenario
        in {
            "current",
            "changed_during_model",
            "changed_during_embedding",
            "quota",
            "late_capability_off",
        }
    )
    assert tokens.await_count == model.await_count  # A paid rejected analysis is still accounted.
