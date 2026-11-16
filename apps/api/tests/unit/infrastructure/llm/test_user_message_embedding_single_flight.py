"""Latency lot 3 — one provider call per message text, whoever asks at once.

At the router's entry two readers ask for the vector of the person's message at
the same moment: the response-context prefetch and the analyzer's broad memory
facts. Both missed the cache and both paid the provider (production timelines,
every turn). Concurrent callers of the same text now share one flight; a failed
flight answers None to all of them and the next caller tries again.
"""

import asyncio
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import pytest

from src.infrastructure.llm.user_message_embedding import clear_cache, get_or_compute_embedding

_VECTOR = [0.1] * 1536
_CLIENT = "src.infrastructure.llm.memory_embeddings.get_memory_embeddings"


@pytest.fixture(autouse=True)
def _clean_cache():
    """The module-level embedding cache is process-global."""
    clear_cache()
    yield
    clear_cache()


@pytest.mark.unit
class TestOneFlightPerText:
    async def test_concurrent_callers_share_one_provider_call(self) -> None:
        released = asyncio.Event()
        calls: list[str] = []

        async def embed(text: str) -> list[float]:
            calls.append(text)
            await released.wait()
            return _VECTOR

        with patch(_CLIENT, return_value=SimpleNamespace(aembed_query=embed)):
            first = asyncio.create_task(
                get_or_compute_embedding("je déménage à Lyon", is_conversational=True)
            )
            second = asyncio.create_task(
                get_or_compute_embedding("je déménage à Lyon", is_conversational=False)
            )
            await asyncio.sleep(0.01)
            released.set()
            assert await first == _VECTOR
            assert await second == _VECTOR

        assert calls == ["je déménage à Lyon"]

    async def test_different_texts_are_different_flights(self) -> None:
        client = SimpleNamespace(aembed_query=AsyncMock(return_value=_VECTOR))
        with patch(_CLIENT, return_value=client):
            await asyncio.gather(
                get_or_compute_embedding("first message", is_conversational=False),
                get_or_compute_embedding("second message", is_conversational=False),
            )

        assert client.aembed_query.await_count == 2

    async def test_a_failed_flight_answers_none_to_all_and_the_next_caller_retries(
        self,
    ) -> None:
        client = SimpleNamespace(
            aembed_query=AsyncMock(side_effect=[RuntimeError("provider down"), _VECTOR])
        )
        with patch(_CLIENT, return_value=client):
            together = await asyncio.gather(
                get_or_compute_embedding("rendez-vous demain", is_conversational=False),
                get_or_compute_embedding("rendez-vous demain", is_conversational=False),
            )
            assert together == [None, None]
            assert (
                await get_or_compute_embedding("rendez-vous demain", is_conversational=False)
                == _VECTOR
            )

        assert client.aembed_query.await_count == 2
