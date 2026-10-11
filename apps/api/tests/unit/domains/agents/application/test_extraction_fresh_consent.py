"""An old frozen runtime is never authority to spend on disabled memory."""

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import pytest
from langchain_core.messages import HumanMessage
from sqlalchemy.ext.asyncio import AsyncSession

from src.domains.agents.middleware.memory_injection import build_psychological_profile
from src.domains.agents.services.memory_extractor import extract_memories_background
from tests.helpers.runtime_context import installed_runtime_context

pytestmark = pytest.mark.unit


async def test_profile_read_does_not_reinject_memory_after_same_turn_optout() -> None:
    actor_id = uuid4()
    db = AsyncMock(spec=AsyncSession)

    @asynccontextmanager
    async def session() -> AsyncIterator[AsyncSession]:
        yield db

    with (
        patch("src.infrastructure.database.session.get_db_context", session),
        patch(
            "src.domains.users.extraction_consent.snapshot_extraction_consent",
            new=AsyncMock(return_value=None),
        ),
        patch(
            "src.domains.memories.repository.MemoryRepository.get_recent_for_user",
            new=AsyncMock(return_value=[]),
        ) as read,
        installed_runtime_context(user_id=actor_id, memory_enabled=True, extraction_revision=4),
    ):
        profile, _, _ = await build_psychological_profile(str(actor_id), "Continue")
    assert profile is None
    read.assert_not_awaited()


async def test_memory_disabled_after_context_creation_is_refused_before_model_or_embeddings() -> (
    None
):
    actor_id = uuid4()
    db = AsyncMock(spec=AsyncSession)

    @asynccontextmanager
    async def session() -> AsyncIterator[AsyncSession]:
        yield db

    with (
        patch("src.infrastructure.database.session.get_db_context", session),
        patch(
            "src.domains.agents.services.memory_extractor.is_capability_enabled",
            new=AsyncMock(return_value=True),
        ),
        patch(
            "src.domains.agents.services.memory_extractor.snapshot_extraction_consent",
            new=AsyncMock(return_value=None),
        ) as consent,
        patch(
            "src.domains.agents.services.memory_extractor.invoke_with_instrumentation",
            new=AsyncMock(),
        ) as invoke,
        patch("src.infrastructure.llm.memory_embeddings.get_memory_embeddings") as embeddings,
        installed_runtime_context(user_id=actor_id, memory_enabled=True, extraction_revision=0),
    ):
        result = await extract_memories_background(
            str(actor_id),
            [HumanMessage(content="Je suis allergique aux arachides depuis mon enfance.")],
            "consent-test",
        )
    assert result == 0
    consent.assert_awaited_once()
    invoke.assert_not_awaited()
    embeddings.assert_not_called()


async def test_optout_during_paid_model_preserves_accounting_and_refuses_late_write() -> None:
    actor_id = uuid4()
    db = AsyncMock(spec=AsyncSession)

    @asynccontextmanager
    async def session() -> AsyncIterator[AsyncSession]:
        yield db

    result = SimpleNamespace(
        text='[{"action":"create","content":"Likes tea","category":"preference"}]'
    )
    with (
        patch("src.infrastructure.database.session.get_db_context", session),
        patch("src.domains.agents.services.memory_embedding_preparation.get_db_context", session),
        patch(
            "src.domains.agents.services.memory_extractor.is_capability_enabled",
            new=AsyncMock(return_value=True),
        ),
        patch(
            "src.domains.agents.services.memory_extractor.snapshot_extraction_consent",
            new=AsyncMock(side_effect=[4, 4, None]),
        ),
        patch(
            "src.domains.agents.services.memory_embedding_preparation.snapshot_extraction_consent",
            new=AsyncMock(return_value=None),
        ),
        patch(
            "src.domains.agents.services.memory_extractor.invoke_with_instrumentation",
            new=AsyncMock(return_value=result),
        ) as invoke,
        patch(
            "src.domains.agents.services.memory_extractor._persist_memory_tokens", new=AsyncMock()
        ) as charge,
        patch(
            "src.domains.agents.services.memory_extractor._maybe_build_health_context",
            new=AsyncMock(return_value=""),
        ),
        patch("src.domains.agents.services.memory_extractor.get_llm"),
        patch(
            "src.domains.agents.services.memory_extractor.get_llm_config_for_agent",
            return_value=SimpleNamespace(model="test-model"),
        ),
        patch(
            "src.domains.agents.services.memory_extractor.tokens_from_response",
            return_value=SimpleNamespace(prompt=3, cached=0, completion=2),
        ),
        patch(
            "src.domains.agents.services.memory_extractor.start_extraction_observation",
            return_value=MagicMock(),
        ),
        patch("src.domains.memories.service._generate_dual_embeddings", new=AsyncMock()) as embed,
        patch("src.domains.memories.service.MemoryService.create_memory", new=AsyncMock()) as write,
        installed_runtime_context(user_id=actor_id, memory_enabled=True, extraction_revision=4),
    ):
        applied = await extract_memories_background(
            str(actor_id),
            [HumanMessage(content="Je bois du thé chaque matin.")],
            "consent-paid",
            query_embedding=[],
        )
    assert applied == 0
    invoke.assert_awaited_once()
    charge.assert_awaited_once()
    embed.assert_not_awaited()
    write.assert_not_awaited()
    db.commit.assert_not_awaited()
