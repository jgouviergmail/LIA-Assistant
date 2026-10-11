"""Scoped cost attribution survives provider cancellation and quota refusal."""

import asyncio
from unittest.mock import AsyncMock, patch
from uuid import uuid4

import pytest

from src.core.exceptions import UsageLimitExceededError
from src.domains.agents.application.memory_creation_embeddings import (
    prepare_memory_creation_embeddings,
)
from src.infrastructure.llm.embedding_context import (
    clear_embedding_context,
    get_embedding_context,
    set_embedding_context,
)

pytestmark = pytest.mark.unit


@pytest.mark.parametrize("failure", ["quota", "cancelled"])
async def test_previous_cost_owner_is_restored_after_preparation_failure(failure: str) -> None:
    prior = get_embedding_context()
    set_embedding_context("previous-owner", "previous-session", run_id="previous-run")
    previous = get_embedding_context()
    actor = uuid4()
    budget = AsyncMock(
        side_effect=UsageLimitExceededError(limit_name="cycle_cost") if failure == "quota" else None
    )
    provider = AsyncMock(side_effect=asyncio.CancelledError())
    guard = AsyncMock()
    try:
        with (
            patch(
                "src.domains.agents.application.memory_creation_embeddings.enforce_usage_limit",
                budget,
            ),
            patch(
                "src.domains.agents.application.memory_creation_embeddings._generate_document_embedding",
                provider,
            ),
            pytest.raises(
                UsageLimitExceededError if failure == "quota" else asyncio.CancelledError
            ),
        ):
            await prepare_memory_creation_embeddings(actor, uuid4(), "Exact fact", "topic", guard)
        assert get_embedding_context() == previous
        assert provider.await_count == (0 if failure == "quota" else 1)
    finally:
        clear_embedding_context()
        if prior is not None:
            set_embedding_context(
                prior.user_id, prior.session_id, prior.conversation_id, prior.run_id
            )
