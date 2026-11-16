"""A resumed turn restores its original choice, or admits that it is unknown."""

from __future__ import annotations

import uuid
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from dataclasses import dataclass, field
from unittest.mock import AsyncMock

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from src.domains.agents.context.runtime_context_builder import build_runtime_context
from src.domains.agents.effects import decision_resume
from src.domains.agents.effects.decision_recorder import decision_recorder
from src.domains.agents.effects.decision_repository import DecisionRepository
from src.domains.agents.effects.decisions import TurnDecision, automatic_turn_engine, turn_decision
from src.domains.agents.effects.models import AgentDecision
from src.domains.agents.models import create_initial_state
from tests.fixtures.conversation_cases import conversation_target

pytestmark = pytest.mark.unit


@dataclass
class _Register:
    row: AgentDecision | None = None
    read_error: Exception | None = None
    close_error: Exception | None = None
    reads: list[str] = field(default_factory=list)
    events: list[str] = field(default_factory=list)


@pytest.fixture
def register(monkeypatch: pytest.MonkeyPatch) -> _Register:
    """Keep the real reader and decision scope, replacing only external I/O."""
    register = _Register()

    @asynccontextmanager
    async def session() -> AsyncIterator[AsyncSession]:
        register.events.append("open")
        try:
            async with AsyncSession() as db:
                yield db
                if register.close_error is not None:
                    raise register.close_error
        finally:
            register.events.append("closed")

    async def read(self: DecisionRepository, run_id: str) -> AgentDecision | None:
        register.reads.append(run_id)
        if register.read_error is not None:
            raise register.read_error
        return register.row

    monkeypatch.setattr(decision_resume, "get_db_context", session)
    monkeypatch.setattr(DecisionRepository, "get_for_run", read)
    monkeypatch.setattr("src.domains.agents.effects.decision_recorder._write_shielded", AsyncMock())
    return register


def _turn(mode: str = "auto") -> TurnDecision:
    return turn_decision(
        run_id="synthetic-resumed-run",
        user_id=uuid.uuid4(),
        thread_id=str(uuid.uuid4()),
        execution_mode=mode,
        automated=False,
    )


def _row(turn: TurnDecision, mode: str | None) -> AgentDecision:
    return AgentDecision(
        run_id=turn.run_id,
        user_id=turn.user_id,
        thread_id=turn.thread_id,
        requested_mode=mode,
        resolution_reason="item_wise",
    )


@pytest.mark.parametrize(
    ("original_mode", "current_mode", "engine", "badge"),
    [
        ("auto", "pipeline", "react", "react"),
        ("auto", "react", "pipeline", "pipeline"),
        ("pipeline", "auto", "pipeline", None),
        ("react", "auto", "react", None),
        ("auto", "auto", "react", "react"),
    ],
)
async def test_original_choice_and_reason_survive_a_changed_preference(
    register: _Register, original_mode: str, current_mode: str, engine: str, badge: str | None
) -> None:
    turn = _turn(current_mode)
    register.row = _row(turn, original_mode)
    assert turn.user_id is not None
    target = conversation_target(turn.user_id, uuid.UUID(turn.thread_id))
    state = create_initial_state(turn.user_id, "session", turn.run_id)
    state["execution_mode"] = engine

    async with decision_recorder(turn):
        await decision_resume.restore_resumed_choice()
        assert register.events == ["open", "closed"]
        assert turn.execution_mode == current_mode, "Only the checkpoint settles the engine."
        context = build_runtime_context(
            state=state, target=target, user_execution_mode=current_mode, resuming=True
        )
        assert context.turn_engine.executed == engine

    assert register.reads == [turn.run_id]
    assert turn.requested_mode == original_mode
    assert turn.resolution_reason == "item_wise"
    assert turn.execution_mode == state["execution_mode"] == engine
    assert automatic_turn_engine(turn) == badge


@pytest.mark.parametrize(
    "unavailable",
    ["missing", "legacy", "invalid", "run", "owner", "thread", "read_error", "close_error"],
)
async def test_unproven_choice_never_uses_the_current_preference(
    register: _Register, unavailable: str
) -> None:
    turn = _turn()
    turn.execution_mode = "react"
    turn.resolution_reason = "requested"
    row = _row(turn, "auto")
    register.row = row
    if unavailable == "missing":
        register.row = None
    elif unavailable == "legacy":
        row.requested_mode = None
    elif unavailable == "invalid":
        row.requested_mode = "not-a-mode"
    elif unavailable == "run":
        row.run_id = "another-run"
    elif unavailable == "owner":
        row.user_id = uuid.uuid4()
    elif unavailable == "thread":
        row.thread_id = str(uuid.uuid4())
    elif unavailable == "read_error":
        register.read_error = RuntimeError("synthetic read failure")
    else:
        register.close_error = RuntimeError("synthetic commit failure")

    async with decision_recorder(turn):
        await decision_resume.restore_resumed_choice()

    assert register.reads == [turn.run_id]
    assert register.events == ["open", "closed"]
    assert turn.requested_mode is None
    assert turn.resolution_reason is None
    assert turn.execution_mode == "react"
    assert automatic_turn_engine(turn) is None


async def test_no_active_turn_opens_no_session(register: _Register) -> None:
    await decision_resume.restore_resumed_choice()

    assert register.reads == []
    assert register.events == []
