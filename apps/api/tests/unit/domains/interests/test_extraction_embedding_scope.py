"""Automatic preparation attributes once per distinct topic and restores its caller."""

import asyncio
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from unittest.mock import AsyncMock, patch
from uuid import uuid4

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.exceptions import UsageLimitExceededError
from src.domains.interests.schemas import ExtractedInterest
from src.domains.interests.services.extraction_storage import prepare_extraction_embeddings
from src.infrastructure.llm.embedding_context import (
    clear_embedding_context,
    get_embedding_context,
    set_embedding_context,
)

pytestmark = pytest.mark.unit


@pytest.mark.parametrize("outcome", ["normal", "cancel", "quota"])
async def test_extraction_preparation_restores_parent_context_and_deduplicates_spend(
    outcome: str,
) -> None:
    owner = uuid4()
    previous = get_embedding_context()
    set_embedding_context(str(uuid4()), "parent-session", run_id="parent-run")
    expected = get_embedding_context()

    @asynccontextmanager
    async def factory() -> AsyncIterator[AsyncSession]:
        yield AsyncMock(spec=AsyncSession)

    async def provider(topic: str) -> None:
        context = get_embedding_context()
        assert context is not None
        assert (context.user_id, context.session_id, context.conversation_id, context.run_id) == (
            str(owner),
            "source-session",
            "source-conversation",
            "source-run",
        )
        if outcome == "cancel":
            raise asyncio.CancelledError
        return None

    actions = [ExtractedInterest(topic="One topic", category="science", confidence=0.95)] * 2
    quota = AsyncMock(
        side_effect=UsageLimitExceededError(limit_name="cycle_cost") if outcome == "quota" else None
    )
    try:
        with (
            patch(
                "src.domains.interests.services.extraction_storage.require_interest_revision",
                new_callable=AsyncMock,
            ),
            patch("src.domains.interests.services.extraction_storage.enforce_usage_limit", quota),
            patch(
                "src.domains.interests.helpers.generate_interest_embedding", side_effect=provider
            ) as embed,
        ):
            if outcome == "normal":
                assert await prepare_extraction_embeddings(
                    factory,
                    owner,
                    7,
                    actions,
                    "source-session",
                    "source-conversation",
                    "source-run",
                ) == {"One topic": None}
            else:
                with pytest.raises(
                    asyncio.CancelledError if outcome == "cancel" else UsageLimitExceededError
                ):
                    await prepare_extraction_embeddings(
                        factory,
                        owner,
                        7,
                        actions,
                        "source-session",
                        "source-conversation",
                        "source-run",
                    )
        quota.assert_awaited_once_with(owner, layer="interest_extraction_embedding")
        assert embed.await_count == int(outcome != "quota")
        assert get_embedding_context() == expected
    finally:
        clear_embedding_context()
        if previous is not None:
            set_embedding_context(
                previous.user_id, previous.session_id, previous.conversation_id, previous.run_id
            )
