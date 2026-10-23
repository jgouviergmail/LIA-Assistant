"""The ReAct call node shapes each call by the turn's exchange rhythm (ADR-308, ADR-311).

For occasional exchanges a call sends exactly what it sent before ADR-308; for
frequent exchanges the turn's context follows the question. The rhythm is read
from the turn's state, which the router wrote at the turn's start, never from
the instance setting; nothing of the layout is written to the checkpoint.
"""

from __future__ import annotations

from typing import Any
from unittest.mock import MagicMock

import pytest
from langchain_core.messages import AIMessage, BaseMessage, HumanMessage, SystemMessage, ToolMessage

from src.core.config import settings
from src.core.constants import DYNAMIC_CONTEXT_MARKER
from src.domains.agents.nodes import react_nodes as rn

pytestmark = pytest.mark.unit

PROMPT = (
    f"You are LIA.\n\n{DYNAMIC_CONTEXT_MARKER} (all variable data below) ---\n\nDate: 2026-09-23"
)
MEMORY = "<UserMemories>Likes tea.</UserMemories>"


@pytest.fixture
def state() -> dict[str, Any]:
    return {
        "messages": [
            HumanMessage(content="earlier", id="h0"),
            AIMessage(content="earlier answer", id="a0"),
            HumanMessage(content="Check my emails.", id="h1"),
            AIMessage(content="", id="a1", tool_calls=[{"name": "t", "args": {}, "id": "c1"}]),
            ToolMessage(content="Retrieved 3 emails.", id="t1", tool_call_id="c1", name="t"),
        ],
        "react_tool_names": [],
        "react_hitl_map": {},
        "react_iteration": 1,
        "react_system_blocks": [PROMPT, MEMORY],
        "react_elapsed_seconds": 0.0,
    }


@pytest.fixture
def sent(monkeypatch: pytest.MonkeyPatch) -> list[list[BaseMessage]]:
    """What the node hands to the model, one list per call."""
    captured: list[list[BaseMessage]] = []
    monkeypatch.setattr(rn, "get_llm", lambda *_a, **_k: MagicMock())
    monkeypatch.setattr(rn, "_rebuild_wrapped_tools", lambda *_a, **_k: [])
    monkeypatch.setattr(rn, "react_slot_provider", lambda: "deepseek")

    async def fake_stream(
        _llm: Any, messages: list[BaseMessage], emit: Any, config: Any
    ) -> AIMessage:
        captured.append(list(messages))
        return AIMessage(content="done", id="out")

    monkeypatch.setattr(
        "src.infrastructure.llm.reasoning_stream.stream_reasoning_events", fake_stream
    )
    return captured


async def test_occasional_exchanges_send_what_a_call_sent_before(
    state: dict[str, Any], sent: list[list[BaseMessage]], monkeypatch: pytest.MonkeyPatch
) -> None:
    # The instance default says frequent: the turn's own rhythm decides.
    monkeypatch.setattr(settings, "react_cross_turn_cache_enabled", True)
    state["exchange_rhythm"] = "occasional"
    await rn.react_call_model_node(state, config={})
    assert sent[0][:2] == [SystemMessage(content=PROMPT), SystemMessage(content=MEMORY)]
    assert [m.id for m in sent[0][2:]] == ["h0", "a0", "h1", "a1", "t1"]


async def test_frequent_exchanges_place_the_turn_s_context_after_the_question(
    state: dict[str, Any], sent: list[list[BaseMessage]], monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(settings, "react_cross_turn_cache_enabled", False)
    state["exchange_rhythm"] = "frequent"
    await rn.react_call_model_node(state, config={})
    messages = sent[0]
    assert "Date:" not in str(messages[0].content)
    question_at = next(i for i, m in enumerate(messages) if m.id == "h1")
    context = messages[question_at + 1]
    assert isinstance(context, SystemMessage)
    assert "Date: 2026-09-23" in str(context.content) and MEMORY in str(context.content)
    assert [m.id for m in messages[question_at + 2 :]] == ["a1", "t1"]


async def test_the_layout_never_reaches_the_checkpoint(
    state: dict[str, Any], sent: list[list[BaseMessage]]
) -> None:
    state["exchange_rhythm"] = "frequent"
    result = await rn.react_call_model_node(state, config={})
    assert [m.id for m in result["messages"]] == ["out"]
    assert state["messages"][2].content == "Check my emails."
    assert state["react_system_blocks"] == [PROMPT, MEMORY]


@pytest.fixture
def horizons(monkeypatch: pytest.MonkeyPatch) -> list[bool]:
    """Whether each model call ran inside the extended cache horizon (ADR-362)."""
    from src.infrastructure.llm.prompt_cache_horizon import extended_horizon_requested

    seen: list[bool] = []
    monkeypatch.setattr(rn, "get_llm", lambda *_a, **_k: MagicMock())
    monkeypatch.setattr(rn, "_rebuild_wrapped_tools", lambda *_a, **_k: [])
    monkeypatch.setattr(rn, "react_slot_provider", lambda: "anthropic")

    async def fake_stream(
        _llm: Any, messages: list[BaseMessage], emit: Any, config: Any
    ) -> AIMessage:
        seen.append(extended_horizon_requested())
        return AIMessage(content="done", id="out")

    monkeypatch.setattr(
        "src.infrastructure.llm.reasoning_stream.stream_reasoning_events", fake_stream
    )
    return seen


async def test_a_frequent_turn_a_person_waits_for_asks_for_the_hour(
    state: dict[str, Any], horizons: list[bool], monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(settings, "prompt_cache_extended_ttl_enabled", True)
    state["exchange_rhythm"] = "frequent"
    await rn.react_call_model_node(state, config={})
    assert horizons == [True]


async def test_an_occasional_turn_keeps_the_default_lifetime(
    state: dict[str, Any], horizons: list[bool], monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(settings, "prompt_cache_extended_ttl_enabled", True)
    state["exchange_rhythm"] = "occasional"
    await rn.react_call_model_node(state, config={})
    assert horizons == [False]


async def test_a_run_nobody_waits_for_keeps_the_default_lifetime(
    state: dict[str, Any], horizons: list[bool], monkeypatch: pytest.MonkeyPatch
) -> None:
    """A routine, a ticket, a relay: the next run is not minutes away."""
    from src.domains.agents.services.streaming.latency_sli import awaited_by_a_person

    monkeypatch.setattr(settings, "prompt_cache_extended_ttl_enabled", True)
    state["exchange_rhythm"] = "frequent"
    with awaited_by_a_person(False):
        await rn.react_call_model_node(state, config={})
    assert horizons == [False]


async def test_the_operator_switch_withdraws_the_hour(
    state: dict[str, Any], horizons: list[bool], monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(settings, "prompt_cache_extended_ttl_enabled", False)
    state["exchange_rhythm"] = "frequent"
    await rn.react_call_model_node(state, config={})
    assert horizons == [False]


async def test_the_loops_model_call_is_counted_by_the_metrics_handler(
    state: dict[str, Any], monkeypatch: pytest.MonkeyPatch
) -> None:
    """Measured on dev 2026-10-22: twelve real ReAct calls reached the ledger and
    no Prometheus LLM metric — the loop never handed its call the per-node metrics
    handler every other node attaches, so tokens, costs and the cache-write counter
    of the one call written for the hour were invisible to the dashboards."""
    from src.infrastructure.observability.callbacks import MetricsCallbackHandler

    configs: list[Any] = []
    monkeypatch.setattr(rn, "get_llm", lambda *_a, **_k: MagicMock())
    monkeypatch.setattr(rn, "_rebuild_wrapped_tools", lambda *_a, **_k: [])
    monkeypatch.setattr(rn, "react_slot_provider", lambda: "anthropic")

    async def fake_stream(
        _llm: Any, messages: list[BaseMessage], emit: Any, config: Any
    ) -> AIMessage:
        configs.append(config)
        return AIMessage(content="done", id="out")

    monkeypatch.setattr(
        "src.infrastructure.llm.reasoning_stream.stream_reasoning_events", fake_stream
    )
    await rn.react_call_model_node(state, config={})
    handlers = [cb for cb in configs[0]["callbacks"] if isinstance(cb, MetricsCallbackHandler)]
    assert [handler.node_name for handler in handlers] == ["react_call_model"]


async def test_the_fallback_call_runs_inside_the_same_horizon(
    state: dict[str, Any], monkeypatch: pytest.MonkeyPatch
) -> None:
    """A stream that yields nothing falls back to ``ainvoke``: same lifetime."""
    from src.infrastructure.llm.prompt_cache_horizon import extended_horizon_requested

    seen: list[bool] = []
    llm = MagicMock()

    async def ainvoke(*_args: Any, **_kwargs: Any) -> AIMessage:
        seen.append(extended_horizon_requested())
        return AIMessage(content="done", id="out")

    llm.ainvoke = ainvoke
    monkeypatch.setattr(rn, "get_llm", lambda *_a, **_k: llm)
    monkeypatch.setattr(rn, "_rebuild_wrapped_tools", lambda *_a, **_k: [])
    monkeypatch.setattr(rn, "react_slot_provider", lambda: "anthropic")

    async def empty_stream(*_args: Any, **_kwargs: Any) -> None:
        return None

    monkeypatch.setattr(
        "src.infrastructure.llm.reasoning_stream.stream_reasoning_events", empty_stream
    )
    monkeypatch.setattr(settings, "prompt_cache_extended_ttl_enabled", True)
    state["exchange_rhythm"] = "frequent"
    await rn.react_call_model_node(state, config={})
    assert seen == [True]
