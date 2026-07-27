"""Triviality detection must only govern conversational input (L2 / D7).

``get_or_compute_embedding`` returns ``None`` for a "trivial" message so the
response pipeline can skip a useless embedding + four extraction LLM calls on
"ok" or "merci". That heuristic was applied to **every** caller, including two
that never pass a conversational message:

- ``person_tools._fetch_person_memories`` embeds a *person name*;
- ``heartbeat.context_aggregator`` embeds an internal search query.

The shipped patterns include ``fine``, ``cool``, ``top``, ``bien``, ``super``
and ``parfait`` — all real surnames. A contact named Fine or Bien therefore lost
every associated memory, silently: ``_fetch_person_memories`` returned ``None``
without ever reaching the database, and the user concluded that LIA "forgot".

These tests pin the boundary in both directions: a conversational "ok" is still
skipped, a person name never is.
"""

from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import pytest

from src.infrastructure.llm.user_message_embedding import (
    clear_cache,
    get_or_compute_embedding,
    is_trivial_message,
)

_VECTOR = [0.1] * 1536


@pytest.fixture(autouse=True)
def _clean_cache():
    """The module-level embedding cache is process-global."""
    clear_cache()
    yield
    clear_cache()


def _fake_embeddings():
    """Stub embedding client returning a fixed vector."""
    return SimpleNamespace(aembed_query=AsyncMock(return_value=_VECTOR))


@pytest.mark.unit
class TestTrivialityIsSurnameBlind:
    """The patterns collide with real surnames — that is the root of D7."""

    @pytest.mark.parametrize("surname", ["Fine", "Cool", "Top", "Bien", "Super", "Parfait"])
    def test_shipped_patterns_match_real_surnames(self, surname: str):
        """Documents the collision the scoping fix exists to neutralize."""
        assert is_trivial_message(surname) is True


@pytest.mark.unit
class TestConversationalScoping:
    """``is_conversational`` decides whether the heuristic applies at all."""

    async def test_conversational_acknowledgement_is_still_skipped(self):
        """The token/latency saving on "ok" must be preserved."""
        with patch(
            "src.infrastructure.llm.memory_embeddings.get_memory_embeddings",
            return_value=_fake_embeddings(),
        ):
            assert await get_or_compute_embedding("ok", is_conversational=True) is None

    async def test_non_conversational_surname_is_embedded(self):
        """A person name is not an acknowledgement — it must reach the model."""
        with patch(
            "src.infrastructure.llm.memory_embeddings.get_memory_embeddings",
            return_value=_fake_embeddings(),
        ):
            assert await get_or_compute_embedding("Fine", is_conversational=False) == _VECTOR

    async def test_conversational_meaningful_message_is_embedded(self):
        """Scoping must not disturb the nominal conversational path."""
        with patch(
            "src.infrastructure.llm.memory_embeddings.get_memory_embeddings",
            return_value=_fake_embeddings(),
        ):
            result = await get_or_compute_embedding(
                "je déménage à Lyon en septembre", is_conversational=True
            )
        assert result == _VECTOR

    async def test_empty_input_is_none_regardless_of_scoping(self):
        """The empty guard precedes the heuristic and is unconditional."""
        assert await get_or_compute_embedding("   ", is_conversational=False) is None


@pytest.mark.unit
class TestPersonMemoriesRegression:
    """The user-visible symptom: a contact whose name matches a pattern."""

    async def test_memories_of_a_contact_named_fine_are_returned(self):
        """Before L2 this returned None without ever querying the database."""
        from src.domains.agents.tools.person_tools import _fetch_person_memories

        memory = SimpleNamespace(content="Fine loves hiking in the Alps")
        repo = MagicMock()
        repo.search_by_relevance = AsyncMock(return_value=[(memory, 0.9)])

        db_ctx = MagicMock()
        db_ctx.__aenter__ = AsyncMock(return_value=MagicMock())
        db_ctx.__aexit__ = AsyncMock(return_value=False)

        with (
            patch(
                "src.infrastructure.llm.memory_embeddings.get_memory_embeddings",
                return_value=_fake_embeddings(),
            ),
            patch(
                "src.infrastructure.database.session.get_db_context",
                return_value=db_ctx,
            ),
            patch(
                "src.domains.memories.repository.MemoryRepository",
                return_value=repo,
            ),
        ):
            result = await _fetch_person_memories(uuid4(), "Fine")

        assert result == ["Fine loves hiking in the Alps"]
        repo.search_by_relevance.assert_awaited_once()
