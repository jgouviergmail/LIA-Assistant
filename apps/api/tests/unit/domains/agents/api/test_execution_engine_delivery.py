"""The real SSE producer names the automatic engine after its recorder closes.

The graph's choice is a deterministic input; the existing stream harness keeps
the production generator, its task boundary, recording scopes and metadata
builders. External persistence and model calls remain hermetic.
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from uuid import UUID

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.config import settings
from src.domains.agents.context.runtime_context_builder import build_runtime_context
from src.domains.agents.effects import decision_resume
from src.domains.agents.effects.decision_repository import DecisionRepository
from src.domains.agents.effects.decisions import TurnDecision, current_turn, note_engine
from src.domains.agents.effects.models import AgentDecision
from src.domains.agents.models import create_initial_state
from src.domains.channels.models import ChannelType, UserChannelBinding
from src.domains.channels.repository import UserChannelBindingRepository
from tests.agents.test_agent_service_stream_characterization import (
    CONVERSATION_ID,
    USER_ID,
    FakeStreamingService,
    Harness,
    _router,
    _token,
)
from tests.fixtures.conversation_cases import conversation_target

pytestmark = [pytest.mark.unit]


@pytest.mark.parametrize(
    ("requested", "engine", "badge"),
    [
        ("auto", "pipeline", "pipeline"),
        ("auto", "react", "react"),
        ("auto", None, None),
        ("pipeline", "pipeline", None),
        ("react", "react", None),
    ],
)
@pytest.mark.parametrize("telegram_active", [False, True])
async def test_the_live_badge_matches_the_archive_with_or_without_telegram(
    monkeypatch: pytest.MonkeyPatch,
    requested: str,
    engine: str | None,
    badge: str | None,
    telegram_active: bool,
) -> None:
    """A linked Telegram account changes neither the browser's engine nor its badge."""
    binding = UserChannelBinding(
        user_id=USER_ID,
        channel_type=ChannelType.TELEGRAM,
        channel_user_id="synthetic-channel",
        is_active=telegram_active,
    )
    lookups: list[UUID] = []

    async def read_active(
        self: UserChannelBindingRepository, user_id: UUID
    ) -> list[UserChannelBinding]:
        lookups.append(user_id)
        return [binding] if telegram_active else []

    monkeypatch.setattr(UserChannelBindingRepository, "get_active_for_user", read_active)
    monkeypatch.setattr(settings, "channels_enabled", True)

    def settle(stream: FakeStreamingService) -> None:
        if engine is not None:
            note_engine(engine, "requested")

    harness = Harness(
        script=[settle, _router("actionable" if engine else "conversation"), _token("Answer")],
        user_execution_mode=requested,
    )
    chunks = await harness.run(monkeypatch)

    assert harness.raised is None
    archived = next(
        metadata for role, _, metadata in harness.conv_service.archived if role == "assistant"
    )
    done = next(chunk.metadata for chunk in chunks if chunk.type == "done")
    assert done is not None
    assert archived.get("execution_engine") == done.get("execution_engine") == badge
    assert lookups == [], "The browser's turn does not consult external-channel bindings."


@pytest.mark.parametrize(
    ("original_mode", "current_mode", "engine", "badge"),
    [
        ("auto", "pipeline", "react", "react"),
        ("auto", "react", "pipeline", "pipeline"),
        ("pipeline", "auto", "pipeline", None),
        ("react", "auto", "react", None),
    ],
)
async def test_resumed_answer_uses_the_original_choice_in_archive_and_done(
    monkeypatch: pytest.MonkeyPatch,
    original_mode: str,
    current_mode: str,
    engine: str,
    badge: str | None,
) -> None:
    """The real preparation restores the durable choice before the graph resumes."""
    run_id = "synthetic-resumed-run"
    state = create_initial_state(USER_ID, "session", run_id)
    state["execution_mode"] = engine
    events: list[str] = []
    turns: list[TurnDecision] = []
    original = AgentDecision(
        run_id=run_id,
        user_id=USER_ID,
        thread_id=str(CONVERSATION_ID),
        requested_mode=original_mode,
        resolution_reason="item_wise",
    )

    @asynccontextmanager
    async def session() -> AsyncIterator[AsyncSession]:
        async with AsyncSession() as db:
            yield db
        events.append("closed")

    async def read(self: DecisionRepository, requested_run_id: str) -> AgentDecision:
        assert requested_run_id == run_id
        events.append("read")
        return original

    def resume(stream: FakeStreamingService) -> None:
        assert events == ["read", "closed"]
        context = build_runtime_context(
            state=state,
            target=conversation_target(USER_ID, CONVERSATION_ID),
            user_execution_mode=current_mode,
            resuming=True,
        )
        assert context.turn_engine.executed == engine
        turn = current_turn()
        assert turn is not None
        turns.append(turn)

    monkeypatch.setattr(decision_resume, "get_db_context", session)
    monkeypatch.setattr(DecisionRepository, "get_for_run", read)
    harness = Harness(
        script=[resume, _token("Answer")],
        state={**state, "_interrupt_resume_data": {"decision": "APPROVE"}},
        original_run_id=run_id,
        user_execution_mode=current_mode,
    )
    chunks = await harness.run(monkeypatch)

    assert harness.raised is None
    archived = next(
        metadata for role, _, metadata in harness.conv_service.archived if role == "assistant"
    )
    done = next(chunk.metadata for chunk in chunks if chunk.type == "done")
    assert done is not None
    assert archived.get("execution_engine") == done.get("execution_engine") == badge
    assert len(turns) == 1
    assert turns[0].requested_mode == original_mode
    assert turns[0].resolution_reason == "item_wise"
    assert turns[0].execution_mode == engine


@pytest.mark.parametrize("redis_names_a_question", [False, True])
async def test_a_turn_without_validated_resume_never_reads_an_earlier_choice(
    monkeypatch: pytest.MonkeyPatch, redis_names_a_question: bool
) -> None:
    """Neither a new turn nor a stale Redis hint borrows an earlier choice."""
    reads: list[str] = []

    async def read(self: DecisionRepository, run_id: str) -> None:
        reads.append(run_id)

    def settle(stream: FakeStreamingService) -> None:
        note_engine("pipeline", "direct")

    monkeypatch.setattr(DecisionRepository, "get_for_run", read)
    harness = Harness(
        script=[settle, _token("Answer")],
        original_run_id="synthetic-stale-run" if redis_names_a_question else None,
        user_execution_mode="auto",
    )
    chunks = await harness.run(monkeypatch)

    assert harness.raised is None
    done = next(chunk.metadata for chunk in chunks if chunk.type == "done")
    assert done is not None
    assert done.get("execution_engine") == "pipeline"
    assert reads == []
