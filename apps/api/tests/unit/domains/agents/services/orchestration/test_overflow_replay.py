"""A turn the model's window refused is compacted and replayed once (lot 15).

Measured before writing it (2026-11-15, read-only): neither production (twelve weeks
of recorded call failures, seven days of logs) nor dev ever hit a context overflow,
the longest prompts reaching a quarter of their window. It stays reachable by
configuration: the compaction threshold is a share of the RESPONSE slot's window, so
a slot on a smaller window overflows before any compaction triggers, turn after
turn, while the person reads « please try again ».

The replay forks from the checkpoint the turn was restored from, so the refused
attempt's writes stay on a branch nobody reads, with a compaction the run's context
forces. Once, and never when the register holds an act of the run: replaying a turn
that acted would act twice.
"""

from __future__ import annotations

import operator
import uuid
from typing import Annotated, Any, TypedDict
from unittest.mock import AsyncMock, patch

import pytest
from langchain_core.exceptions import ContextOverflowError
from langchain_core.messages import AIMessage, BaseMessage, HumanMessage
from langgraph.checkpoint.memory import InMemorySaver
from langgraph.graph import END, START, StateGraph
from langgraph.runtime import Runtime
from prometheus_client import REGISTRY

from src.core.config import settings
from src.domains.agents.context.runtime_context import LiaRuntimeContext
from src.domains.agents.services.orchestration import overflow_replay
from src.domains.agents.services.orchestration.overflow_replay import (
    replay_refusal,
    stream_fresh_turn,
)

pytestmark = pytest.mark.unit

PRESERVED = settings.compaction_preserve_recent_messages
#: One whole exchange before the kept tail: what a compaction can summarise.
COMPACTABLE = PRESERVED + 2
CONTEXT = LiaRuntimeContext(user_id=uuid.UUID(int=1), thread_id="t", conversation_id="c")
CONFIG: dict[str, Any] = {"configurable": {"thread_id": "t"}, "metadata": {"run_id": "run-2"}}


class _State(TypedDict, total=False):
    log: Annotated[list[str], operator.add]
    want: str


def _entry(state: _State, runtime: Runtime[LiaRuntimeContext]) -> dict[str, Any]:
    return {"log": ["compacted" if runtime.context.compaction_forced else "entry"]}


def _partial(state: _State, runtime: Runtime[LiaRuntimeContext]) -> dict[str, Any]:
    return {"log": [f"partial:{runtime.context.compaction_forced}"]}


def _model(state: _State, runtime: Runtime[LiaRuntimeContext]) -> dict[str, Any]:
    refused = state["want"] == "always" or (
        state["want"] == "big" and not runtime.context.compaction_forced
    )
    if refused:
        raise ContextOverflowError("the window refused the request")
    return {"log": ["answered"]}


def _app() -> Any:
    graph = StateGraph(_State, context_schema=LiaRuntimeContext)
    graph.add_node("entry", _entry)
    graph.add_node("partial", _partial)
    graph.add_node("model", _model)
    graph.add_edge(START, "entry")
    graph.add_edge("entry", "partial")
    graph.add_edge("partial", "model")
    graph.add_edge("model", END)
    return graph.compile(checkpointer=InMemorySaver())


async def _restored(app: Any) -> str:
    """Turn 1 answers; the checkpoint it leaves is the one turn 2 is restored from."""
    first = {"configurable": {"thread_id": "t"}, "metadata": {"run_id": "run-1"}}
    await app.ainvoke({"want": "ok", "log": ["turn1"]}, first, context=CONTEXT)
    return str((await app.aget_state(CONFIG)).config["configurable"]["checkpoint_id"])


def _shaped(count: int, **extra: Any) -> dict[str, Any]:
    """The state the loader handed the stream: ``count`` messages, the request last."""
    messages: list[BaseMessage] = [
        HumanMessage(f"m{i}", id=f"m{i}") if i % 2 == 0 else AIMessage(f"m{i}", id=f"m{i}")
        for i in range(count - 1)
    ]
    return {"messages": [*messages, HumanMessage("the request", id="request")], **extra}


async def _turn(app: Any, want: str, checkpoint: str | None, state: dict[str, Any]) -> None:
    async for _ in stream_fresh_turn(
        app,
        {"want": want, "log": ["turn2"]},
        CONFIG,
        CONTEXT,
        state=state,
        run_id="run-2",
        restored_checkpoint_id=checkpoint,
    ):
        pass


def _counted(outcome: str) -> float:
    value = REGISTRY.get_sample_value("compaction_overflow_replays_total", {"outcome": outcome})
    return value or 0.0


async def _log(app: Any) -> list[str]:
    return list((await app.aget_state(CONFIG)).values["log"])


class TestTheReplay:
    async def test_the_refused_turn_is_compacted_and_answered_from_where_it_started(
        self,
    ) -> None:
        app = _app()
        checkpoint = await _restored(app)
        before = _counted("replayed")

        with patch.object(
            overflow_replay, "run_may_have_acted", AsyncMock(return_value=False)
        ) as acted:
            await _turn(app, "big", checkpoint, _shaped(COMPACTABLE))

        # The refused attempt's « entry, partial:False » stayed on its own branch.
        assert await _log(app) == [
            "turn1",
            "entry",
            "partial:False",
            "answered",
            "turn2",
            "compacted",
            "partial:True",
            "answered",
        ]
        acted.assert_awaited_once_with("run-2")
        assert _counted("replayed") == before + 1

    async def test_a_turn_that_acted_is_never_replayed(self) -> None:
        app = _app()
        checkpoint = await _restored(app)
        before = _counted("refused_acted")

        with (
            patch.object(overflow_replay, "run_may_have_acted", AsyncMock(return_value=True)),
            pytest.raises(ContextOverflowError),
        ):
            await _turn(app, "big", checkpoint, _shaped(COMPACTABLE))

        assert "compacted" not in await _log(app)
        assert _counted("refused_acted") == before + 1

    async def test_a_replay_the_window_refuses_again_is_never_replayed_twice(self) -> None:
        app = _app()
        checkpoint = await _restored(app)
        before = _counted("replay_overflowed")

        with (
            patch.object(overflow_replay, "run_may_have_acted", AsyncMock(return_value=False)),
            pytest.raises(ContextOverflowError),
        ):
            await _turn(app, "always", checkpoint, _shaped(COMPACTABLE))

        assert (await _log(app)).count("compacted") == 1
        assert _counted("replay_overflowed") == before + 1

    async def test_a_turn_that_fits_streams_once_and_reads_no_register(self) -> None:
        app = _app()
        checkpoint = await _restored(app)

        with patch.object(overflow_replay, "run_may_have_acted", AsyncMock()) as acted:
            await _turn(app, "ok", checkpoint, _shaped(COMPACTABLE))

        assert (await _log(app))[-4:] == ["turn2", "entry", "partial:False", "answered"]
        acted.assert_not_awaited()


class TestWhatRefusesAReplay:
    """The cheap facts first; the register is read only when they all allow it."""

    @pytest.mark.parametrize(
        ("state", "checkpoint", "enabled", "reason"),
        [
            pytest.param(_shaped(COMPACTABLE), "cp", False, "compaction_disabled", id="off"),
            pytest.param(_shaped(COMPACTABLE), None, True, "no_checkpoint", id="first-turn"),
            pytest.param(
                _shaped(PRESERVED + 1),
                "cp",
                True,
                "nothing_to_compact",
                id="one-exchange-kept-whole",
            ),
            pytest.param(
                _shaped(COMPACTABLE, pending_tool_confirmation={"tool": "x"}),
                "cp",
                True,
                "hitl_pending",
                id="question-pending",
            ),
        ],
    )
    async def test_a_replay_compaction_cannot_help_is_refused_unread(
        self,
        monkeypatch: pytest.MonkeyPatch,
        state: dict[str, Any],
        checkpoint: str | None,
        enabled: bool,
        reason: str,
    ) -> None:
        monkeypatch.setattr(settings, "compaction_enabled", enabled)
        with patch.object(overflow_replay, "run_may_have_acted", AsyncMock()) as acted:
            refusal = await replay_refusal(state, run_id="run-2", restored_checkpoint_id=checkpoint)

        assert refusal == reason
        acted.assert_not_awaited()

    async def test_the_register_decides_last(self) -> None:
        with patch.object(overflow_replay, "run_may_have_acted", AsyncMock(return_value=True)):
            refusal = await replay_refusal(
                _shaped(COMPACTABLE), run_id="run-2", restored_checkpoint_id="cp"
            )

        assert refusal == "acted"
