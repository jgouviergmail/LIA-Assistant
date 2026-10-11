"""Embedding requests must finish before the short consent-locked write section."""

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from src.domains.agents.services.memory_embedding_preparation import prepare_memory_embeddings
from src.domains.memories.prepared_embeddings import PreparedMemoryEmbeddings
from src.domains.memories.schemas import ExtractedMemory
from src.domains.memories.service import MemoryService

pytestmark = pytest.mark.unit


async def test_prepared_vectors_are_used_without_a_second_provider_request() -> None:
    prepared = PreparedMemoryEmbeddings({("I like tea", "tea"): ([0.1], [0.2])})
    db = AsyncMock(spec=AsyncSession)
    db.add = MagicMock()
    with patch(
        "src.domains.memories.service._generate_dual_embeddings", new=AsyncMock()
    ) as provider:
        memory = await MemoryService(db, embedder=prepared.resolve).create_memory(
            uuid4(), "I like tea", "preference", trigger_topic="tea"
        )
    assert memory.embedding == [0.1] and memory.keyword_embedding == [0.2]
    provider.assert_not_awaited()


async def test_changed_write_inputs_fail_without_an_unapproved_provider_fallback() -> None:
    prepared = PreparedMemoryEmbeddings({("I like tea", "tea"): ([0.1], [0.2])})
    with pytest.raises(ValueError):
        await prepared.resolve("A different current fact", "tea")


async def test_revoked_consent_stops_new_embedding_work_between_actions() -> None:
    db = AsyncMock(spec=AsyncSession)
    open_sessions = 0

    @asynccontextmanager
    async def session() -> AsyncIterator[AsyncSession]:
        nonlocal open_sessions
        open_sessions += 1
        try:
            yield db
        finally:
            open_sessions -= 1

    async def embed(content: str, topic: str) -> tuple[list[float], list[float]]:
        assert open_sessions == 0, "Provider work must hold no database session or consent lock"
        return [0.1], [0.2]

    provider = AsyncMock(side_effect=embed)
    actions = [
        ExtractedMemory(action="create", content="A", category="preference"),
        ExtractedMemory(action="create", content="B", category="preference"),
    ]
    with (
        patch("src.domains.agents.services.memory_embedding_preparation.get_db_context", session),
        patch(
            "src.domains.agents.services.memory_embedding_preparation.snapshot_extraction_consent",
            new=AsyncMock(side_effect=[4, None]),
        ) as consent,
    ):
        prepared = await prepare_memory_embeddings(
            uuid4(), actions, provider, extraction_revision=4
        )
    assert provider.await_count == 1
    assert consent.await_count == 2
    with pytest.raises(ValueError):
        await prepared.resolve("A", "")
