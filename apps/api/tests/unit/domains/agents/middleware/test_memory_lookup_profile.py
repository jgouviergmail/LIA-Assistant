"""A memory LOOKUP is ranked on its question, not on recency (ADR-313).

The phone's ``recall_memories`` lookup and the owner call's context handed their
query to the chat's profile builder with no vector; the builder then fell back
to the ten most RECENT memories — « what do I drink » answered with whatever
was newest. Both now go through ``build_profile_for_lookup``, which embeds the
question as a lookup key first.
"""

from __future__ import annotations

from typing import Any
from unittest.mock import AsyncMock, patch
from uuid import uuid4

import pytest

from src.domains.agents.middleware import memory_injection
from src.domains.memories.emotional_state import EmotionalState

_VECTOR = [0.3] * 4


@pytest.mark.unit
class TestBuildProfileForLookup:
    async def test_the_question_is_embedded_and_ranks_the_profile(self) -> None:
        embed = AsyncMock(return_value=_VECTOR)
        build = AsyncMock(return_value=("profile", EmotionalState.NEUTRAL, None))

        with (
            patch("src.domains.memories.search.embed_lookup", embed),
            patch.object(memory_injection, "build_psychological_profile", build),
        ):
            result = await memory_injection.build_profile_for_lookup("u1", "what do I drink")

        assert result == ("profile", EmotionalState.NEUTRAL, None)
        embed.assert_awaited_once_with("what do I drink", user_id="u1")
        assert build.await_args.kwargs["query_embedding"] == _VECTOR

    async def test_without_a_vector_the_recency_fallback_still_answers(self) -> None:
        build = AsyncMock(return_value=("recent", EmotionalState.NEUTRAL, None))

        with (
            patch("src.domains.memories.search.embed_lookup", AsyncMock(return_value=None)),
            patch.object(memory_injection, "build_psychological_profile", build),
        ):
            result = await memory_injection.build_profile_for_lookup("u1", "anything")

        assert result[0] == "recent"
        assert build.await_args.kwargs["query_embedding"] is None


@pytest.mark.unit
class TestTheVoiceDoorsRankOnTheQuestion:
    async def test_the_phone_lookup_reader_goes_through_the_lookup_door(self) -> None:
        from src.domains.agents.telephony import live_tools

        seen: dict[str, Any] = {}

        async def lookup(user_id: str, query: str) -> tuple[str, EmotionalState, None]:
            seen["args"] = (user_id, query)
            return "- likes tea", EmotionalState.NEUTRAL, None

        with patch.object(memory_injection, "build_profile_for_lookup", lookup):
            result = await live_tools.build_psychological_profile("u2", "what do I drink")

        assert seen["args"] == ("u2", "what do I drink")
        assert result[0] == "- likes tea"

    async def test_the_owner_call_context_ranks_on_its_objective(self) -> None:
        from src.domains.agents.tools.telephony_self_tools import memory_fetcher_for

        seen: dict[str, Any] = {}

        async def lookup(user_id: str, query: str) -> tuple[str, EmotionalState, None]:
            seen["query"] = query
            return "- dentist on Mondays\n\n- likes tea", EmotionalState.NEUTRAL, None

        owner = uuid4()
        with patch.object(memory_injection, "build_profile_for_lookup", lookup):
            lines = await memory_fetcher_for(owner, objective="plan the week")()
            await memory_fetcher_for(owner, objective="")()

        assert lines == ["- dentist on Mondays", "- likes tea"]
        # An empty objective is a catch-up call, still a ranked lookup.
        assert seen["query"] == "catch-up call"
