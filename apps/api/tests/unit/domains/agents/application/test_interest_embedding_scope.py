"""A cancelled or refused source call restores its parent's embedding attribution."""

import asyncio
from unittest.mock import AsyncMock, patch
from uuid import uuid4

import pytest

from src.core.exceptions import UsageLimitExceededError
from src.domains.agents.application.interest_embeddings import prepare_interest_embedding
from src.infrastructure.llm.embedding_context import (
    clear_embedding_context,
    get_embedding_context,
    set_embedding_context,
)

pytestmark = pytest.mark.unit


@pytest.mark.parametrize("outcome", ["normal", "cancel", "quota"])
async def test_interest_embedding_scope_restores_the_outer_owner(outcome: str) -> None:
    previous = get_embedding_context()
    owner, command, parent = uuid4(), uuid4(), uuid4()
    set_embedding_context(str(parent), "parent-session", run_id="parent-run")
    expected = get_embedding_context()
    calls: list[str] = []

    async def provider(topic: str) -> None:
        context = get_embedding_context()
        assert (
            context is not None and context.user_id == str(owner) and context.run_id == str(command)
        )
        calls.append(topic)
        if outcome == "cancel":
            raise asyncio.CancelledError
        return None

    quota = AsyncMock(
        side_effect=UsageLimitExceededError(limit_name="cycle_cost") if outcome == "quota" else None
    )
    try:
        with (
            patch(
                "src.domains.interests.helpers.generate_interest_embedding", side_effect=provider
            ),
            patch("src.domains.agents.application.interest_embeddings.enforce_usage_limit", quota),
        ):
            if outcome == "normal":
                assert (
                    await prepare_interest_embedding(owner, command, "Owned topic", AsyncMock())
                    is None
                )
            else:
                with pytest.raises(
                    asyncio.CancelledError if outcome == "cancel" else UsageLimitExceededError
                ):
                    await prepare_interest_embedding(owner, command, "Owned topic", AsyncMock())
        assert get_embedding_context() == expected
        assert calls == ([] if outcome == "quota" else ["Owned topic"])
    finally:
        clear_embedding_context()
        if previous is not None:
            set_embedding_context(
                previous.user_id, previous.session_id, previous.conversation_id, previous.run_id
            )
