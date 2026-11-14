"""An import embeds by batches — each one under the fence and both spending ceilings.

A creation embeds its two texts one call each; an import of several hundred memories
would take minutes that way. It asks the provider by batches instead, and nothing of
what a single creation guarantees is lost: the fence and the usage ceilings are asked
before EVERY paid call, the spend is attributed to the account, and a failed call
fails the import rather than storing memories no search can find.
"""

from __future__ import annotations

from unittest.mock import AsyncMock
from uuid import uuid4

import pytest

from src.core.constants import MEMORY_IMPORT_EMBEDDING_BATCH_SIZE
from src.core.exceptions import UsageLimitExceededError
from src.domains.memories import creation_embeddings
from src.domains.memories.creation_embeddings import prepare_memory_import_embeddings
from src.infrastructure.llm.embedding_context import (
    clear_embedding_context,
    get_embedding_context,
    set_embedding_context,
)

pytestmark = pytest.mark.unit


def _vector(text: str) -> list[float]:
    return [float(len(text)), 1.0]


@pytest.fixture
def provider(monkeypatch: pytest.MonkeyPatch) -> AsyncMock:
    calls = AsyncMock(side_effect=lambda texts: [_vector(text) for text in texts])
    monkeypatch.setattr(creation_embeddings, "generate_document_embeddings", calls)
    return calls


@pytest.fixture
def ceiling(monkeypatch: pytest.MonkeyPatch) -> AsyncMock:
    asked = AsyncMock()
    monkeypatch.setattr(creation_embeddings, "enforce_usage_limit", asked)
    return asked


async def test_each_memory_resolves_to_its_two_vectors(
    provider: AsyncMock, ceiling: AsyncMock
) -> None:
    pairs = [("A fact with a topic", "topic"), ("A fact with none", "")]

    prepared = await prepare_memory_import_embeddings(uuid4(), uuid4(), pairs, AsyncMock())

    assert await prepared.resolve("A fact with a topic", "topic") == (
        _vector("A fact with a topic"),
        _vector("topic"),
    )
    # No topic, no second vector — and no blank text sent to the provider.
    assert await prepared.resolve("A fact with none", "") == (_vector("A fact with none"), None)
    assert provider.await_args_list[0].args[0] == [
        "A fact with a topic",
        "topic",
        "A fact with none",
    ]


async def test_a_text_several_memories_share_is_paid_for_once(
    provider: AsyncMock, ceiling: AsyncMock
) -> None:
    pairs = [("First fact", "family"), ("Second fact", "family"), ("family", "")]

    prepared = await prepare_memory_import_embeddings(uuid4(), uuid4(), pairs, AsyncMock())

    sent = [text for call in provider.await_args_list for text in call.args[0]]
    assert sent == ["First fact", "family", "Second fact"]
    assert await prepared.resolve("family", "") == (_vector("family"), None)


async def test_the_fence_and_the_ceilings_are_asked_before_every_batch(
    provider: AsyncMock, ceiling: AsyncMock
) -> None:
    user_id = uuid4()
    order: list[str] = []
    fence = AsyncMock(side_effect=lambda: order.append("fence"))
    ceiling.side_effect = lambda *_args, **_kwargs: order.append("ceiling")
    provider.side_effect = lambda texts: order.append("provider") or [_vector(t) for t in texts]
    pairs = [
        (f"Fact number {index}", "") for index in range(MEMORY_IMPORT_EMBEDDING_BATCH_SIZE + 1)
    ]

    await prepare_memory_import_embeddings(user_id, uuid4(), pairs, fence)

    assert order == ["fence", "ceiling", "provider"] * 2
    assert [len(call.args[0]) for call in provider.await_args_list] == [
        MEMORY_IMPORT_EMBEDDING_BATCH_SIZE,
        1,
    ]
    assert all(call.args[0] == user_id for call in ceiling.await_args_list)


async def test_the_spend_is_attributed_to_the_account_for_the_whole_import(
    provider: AsyncMock, ceiling: AsyncMock
) -> None:
    user_id, command_id = uuid4(), uuid4()
    seen: list[tuple[str | None, str | None]] = []

    def record(texts: list[str]) -> list[list[float]]:
        context = get_embedding_context()
        seen.append((context.user_id, context.run_id) if context else (None, None))
        return [_vector(text) for text in texts]

    provider.side_effect = record
    set_embedding_context("someone-else", "their-session", run_id="their-run")
    try:
        await prepare_memory_import_embeddings(user_id, command_id, [("A fact", "")], AsyncMock())

        assert seen == [(str(user_id), str(command_id))]
        # The caller's own attribution is handed back as it was.
        restored = get_embedding_context()
        assert restored is not None and restored.user_id == "someone-else"
    finally:
        clear_embedding_context()


async def test_a_refused_ceiling_stops_before_the_provider_is_paid(
    provider: AsyncMock, ceiling: AsyncMock
) -> None:
    ceiling.side_effect = UsageLimitExceededError(limit_name="cycle_cost")

    with pytest.raises(UsageLimitExceededError):
        await prepare_memory_import_embeddings(uuid4(), uuid4(), [("A fact", "")], AsyncMock())

    provider.assert_not_awaited()
    assert get_embedding_context() is None


async def test_nothing_to_import_asks_nobody(provider: AsyncMock, ceiling: AsyncMock) -> None:
    fence = AsyncMock()

    prepared = await prepare_memory_import_embeddings(uuid4(), uuid4(), [], fence)

    assert prepared.vectors == {}
    fence.assert_not_awaited()
    ceiling.assert_not_awaited()
    provider.assert_not_awaited()


class TestTheBatchDoorFailsRatherThanStoreTheUnsearchable:
    async def test_a_provider_failure_is_raised(self, monkeypatch: pytest.MonkeyPatch) -> None:
        from src.domains.memories import service

        class Failing:
            async def aembed_documents(self, texts: list[str]) -> list[list[float]]:
                raise RuntimeError("provider down")

        monkeypatch.setattr(
            "src.infrastructure.llm.memory_embeddings.get_memory_embeddings", lambda: Failing()
        )

        with pytest.raises(RuntimeError):
            await service.generate_document_embeddings(["A fact"])

    async def test_an_answer_of_another_length_is_refused(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        from src.domains.memories import service

        class Short:
            async def aembed_documents(self, texts: list[str]) -> list[list[float]]:
                return [[0.0]]

        monkeypatch.setattr(
            "src.infrastructure.llm.memory_embeddings.get_memory_embeddings", lambda: Short()
        )

        with pytest.raises(ValueError, match="2 texts"):
            await service.generate_document_embeddings(["A fact", "Another fact"])
