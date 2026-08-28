"""The ReAct loop must know the user's memory, exactly as the pipeline does.

Measured in production on 2026-08-28: a standing instruction stored in long-term
memory ("do not tell me you will do it — do it") had no effect whatsoever in
ReAct mode. The reason was structural, not statistical: ``injected_memories``
was DECLARED in ``MessagesState``, READ by the ReAct setup, and written by
nobody — anywhere in the repository. The loop therefore reasoned with no memory
at all, while the pipeline's response node received the full psychological
profile through ``build_psychological_profile``.

The profile reaching only the response node is not parity either: in ReAct the
final message is handed to that node as AUTHORITATIVE, so a rule arriving there
can reword a promise but never turn it into an action. A behavioural rule has to
be present where the behaviour is decided — inside the loop.

This is the same cross-mode gap that was already closed for journal directives
(``react_journal_directives_failed`` block, "the ReAct reasoning loop was blind
to behavioural directives"). Memory gets the identical treatment, through the
identical builder — never a second implementation.
"""

from __future__ import annotations

from typing import Any

import pytest
from langchain_core.messages import HumanMessage

from src.domains.agents.nodes import react_context

pytestmark = [pytest.mark.unit]

PROFILE = "### RÈGLES DE FONCTIONNEMENT\n- Ne dis pas que tu vas le faire : fais-le."


def _state(text: str = "Combien de temps durent mes escales ?") -> dict[str, Any]:
    return {"messages": [HumanMessage(content=text)]}


def _config(**overrides: Any) -> dict[str, Any]:
    configurable = {
        "langgraph_user_id": "11111111-1111-1111-1111-111111111111",
        "thread_id": "thread-1",
        "user_memory_enabled": True,
    }
    configurable.update(overrides)
    return {"configurable": configurable}


@pytest.fixture
def profile_builder(monkeypatch: pytest.MonkeyPatch) -> list[dict[str, Any]]:
    """Capture the calls made to the shared profile builder."""
    calls: list[dict[str, Any]] = []

    async def _fake_profile(**kwargs: Any) -> tuple[str, Any, None]:
        calls.append(kwargs)
        from src.domains.memories.emotional_state import EmotionalState

        return PROFILE, EmotionalState.NEUTRAL, None

    async def _fake_embedding(**_kwargs: Any) -> list[float]:
        return [0.0] * 8

    monkeypatch.setattr(react_context, "build_psychological_profile", _fake_profile)
    monkeypatch.setattr(react_context, "get_or_compute_embedding", _fake_embedding)
    return calls


class TestTheLoopReceivesTheProfile:
    async def test_the_profile_becomes_a_system_block(
        self, profile_builder: list[dict[str, Any]]
    ) -> None:
        block = await react_context.build_memory_profile_block(_state(), _config())

        assert block is not None
        assert PROFILE in block

    async def test_it_uses_the_pipeline_builder_with_the_pipeline_settings(
        self, profile_builder: list[dict[str, Any]]
    ) -> None:
        """One implementation for both modes — a second one would drift."""
        from src.core.config import settings

        await react_context.build_memory_profile_block(_state(), _config())

        assert len(profile_builder) == 1
        call = profile_builder[0]
        assert call["limit"] == settings.memory_max_results
        assert call["min_score"] == settings.memory_min_search_score
        assert call["query_embedding"] is not None, "the shared embedding must be reused"


class TestTheUserRemainsInControl:
    async def test_memory_disabled_by_the_user_injects_nothing(
        self, profile_builder: list[dict[str, Any]]
    ) -> None:
        block = await react_context.build_memory_profile_block(
            _state(), _config(user_memory_enabled=False)
        )

        assert block is None
        assert profile_builder == [], "no search may run when memory is off"

    async def test_no_user_id_injects_nothing(self, profile_builder: list[dict[str, Any]]) -> None:
        block = await react_context.build_memory_profile_block(
            _state(), _config(langgraph_user_id="")
        )

        assert block is None
        assert profile_builder == []

    async def test_a_trivial_message_skips_the_embedding_not_the_profile(
        self, profile_builder: list[dict[str, Any]]
    ) -> None:
        """Exactly the pipeline's gating: a standing rule applies to "ok" too.

        Triviality saves the embedding call; the builder then falls back to the
        user's recent memories. Skipping the whole profile would make the loop
        LESS memory-aware than the other mode.
        """
        block = await react_context.build_memory_profile_block(_state("ok"), _config())

        assert block is not None
        assert profile_builder[0]["query_embedding"] is None, "no vector was paid for"


class TestDegradationMatchesThePipeline:
    async def test_an_embedding_failure_still_yields_a_profile(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """No vector is a worse search, not an absence of memory."""
        calls: list[dict[str, Any]] = []

        async def _fake_profile(**kwargs: Any) -> tuple[str, Any, None]:
            calls.append(kwargs)
            from src.domains.memories.emotional_state import EmotionalState

            return PROFILE, EmotionalState.NEUTRAL, None

        async def _broken_embedding(**_kwargs: Any) -> list[float]:
            raise RuntimeError("embedding provider down")

        monkeypatch.setattr(react_context, "build_psychological_profile", _fake_profile)
        monkeypatch.setattr(react_context, "get_or_compute_embedding", _broken_embedding)

        block = await react_context.build_memory_profile_block(_state(), _config())

        assert block is not None and PROFILE in block
        assert calls[0]["query_embedding"] is None


class TestItNeverBreaksTheTurn:
    async def test_a_failing_profile_build_is_swallowed_loudly(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Memory is context, not a dependency: its failure must not kill the turn."""

        async def _boom(**_kwargs: Any) -> tuple[str, Any, None]:
            raise RuntimeError("pgvector unavailable")

        async def _fake_embedding(**_kwargs: Any) -> list[float]:
            return [0.0] * 8

        monkeypatch.setattr(react_context, "build_psychological_profile", _boom)
        monkeypatch.setattr(react_context, "get_or_compute_embedding", _fake_embedding)

        assert await react_context.build_memory_profile_block(_state(), _config()) is None


class TestTheDeadKeyIsGone:
    def test_injected_memories_no_longer_exists_anywhere(self) -> None:
        """It was declared, read, and never written — the definition of dead."""
        import inspect

        from src.domains.agents import models
        from src.domains.agents.nodes import react_nodes

        assert "injected_memories" not in models.MessagesState.__annotations__
        assert "injected_memories" not in inspect.getsource(react_nodes)
        assert "injected_memories" not in inspect.getsource(react_context)


class TestTheSetupWiresIt:
    def test_react_setup_asks_for_the_memory_block(self) -> None:
        """A builder nobody calls protects nothing."""
        import inspect

        from src.domains.agents.nodes import react_nodes

        source = inspect.getsource(react_nodes.react_setup_node)
        assert "build_memory_profile_block" in source
