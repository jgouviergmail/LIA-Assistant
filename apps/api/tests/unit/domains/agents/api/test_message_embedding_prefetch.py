"""Latency lot 3 — the person's message is embedded while the turn prepares.

The router's readers find the vector cached instead of computing it on the
critical path. The prefetch is the turn's: it runs under the turn's run id, and
the turn's scope waits for it, so its spend reaches the tracker before it files.
"""

import asyncio
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import pytest
from langchain_core.messages import AIMessage, HumanMessage

from src.domains.agents.api import message_embedding_prefetch as module
from src.domains.agents.api.message_embedding_prefetch import MessageEmbeddingPrefetch
from src.infrastructure.llm.embedding_context import get_embedding_context
from src.infrastructure.llm.user_message_embedding import clear_cache, get_or_compute_embedding

_VECTOR = [0.2] * 1536
_CLIENT = "src.infrastructure.llm.memory_embeddings.get_memory_embeddings"
_TEXT = "Quel temps fera-t-il demain à Lyon ?"


@pytest.fixture(autouse=True)
def _clean_cache():
    """The module-level embedding cache is process-global."""
    clear_cache()
    yield
    clear_cache()


def _state(*messages: object) -> dict[str, object]:
    return {"messages": list(messages)}


@pytest.mark.unit
class TestMessageEmbeddingPrefetch:
    async def test_the_message_is_embedded_once_and_the_router_finds_it_cached(self) -> None:
        client = SimpleNamespace(aembed_query=AsyncMock(return_value=_VECTOR))
        with patch(_CLIENT, return_value=client):
            async with MessageEmbeddingPrefetch() as prefetch:
                prefetch.start(
                    _state(HumanMessage(content=_TEXT)), "u1", "s1", "run-1", resuming=False
                )
            # A reader of the router: same text, no second provider call.
            assert await get_or_compute_embedding(_TEXT, is_conversational=False) == _VECTOR

        client.aembed_query.assert_awaited_once_with(_TEXT)

    async def test_a_resumed_turn_starts_nothing(self) -> None:
        client = SimpleNamespace(aembed_query=AsyncMock(return_value=_VECTOR))
        with patch(_CLIENT, return_value=client):
            async with MessageEmbeddingPrefetch() as prefetch:
                prefetch.start(
                    _state(HumanMessage(content=_TEXT)), "u1", "s1", "run-1", resuming=True
                )

        client.aembed_query.assert_not_awaited()

    async def test_a_last_message_that_is_not_the_persons_starts_nothing(self) -> None:
        client = SimpleNamespace(aembed_query=AsyncMock(return_value=_VECTOR))
        with patch(_CLIENT, return_value=client):
            async with MessageEmbeddingPrefetch() as prefetch:
                prefetch.start(
                    _state(AIMessage(content="Bonjour")), "u1", "s1", "run-1", resuming=False
                )
                prefetch.start(_state(), "u1", "s1", "run-1", resuming=False)

        client.aembed_query.assert_not_awaited()

    async def test_the_scope_waits_for_a_running_prefetch_before_closing(self) -> None:
        finished: list[str] = []

        async def embed(text: str) -> list[float]:
            await asyncio.sleep(0.05)
            finished.append(text)
            return _VECTOR

        with patch(_CLIENT, return_value=SimpleNamespace(aembed_query=embed)):
            async with MessageEmbeddingPrefetch() as prefetch:
                prefetch.start(
                    _state(HumanMessage(content=_TEXT)), "u1", "s1", "run-1", resuming=False
                )
            # Leaving the scope is where the tracker files: the spend is in by now.
            assert finished == [_TEXT]

    async def test_the_vector_is_computed_under_the_turns_run(self) -> None:
        seen: list[object] = []

        async def compute(**_kwargs: object) -> list[float]:
            seen.append(get_embedding_context())
            return _VECTOR

        with patch.object(module, "get_or_compute_embedding", side_effect=compute):
            async with MessageEmbeddingPrefetch() as prefetch:
                prefetch.start(
                    _state(HumanMessage(content=_TEXT)), "u1", "s1", "run-7", resuming=False
                )

        assert [(ctx.user_id, ctx.run_id) for ctx in seen] == [("u1", "run-7")]
        # The context is the prefetch's own: the caller's is untouched.
        assert get_embedding_context() is None
