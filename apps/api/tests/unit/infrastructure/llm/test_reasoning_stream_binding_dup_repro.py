"""Pin down the on_llm_end double-fire on the reasoning-streaming path.

Confirmed from live provenance logs: the initiative LLM run fires on_chat_model_start
and on_llm_end TWICE with parent_run_id=None (re-rooted), while every other node fires
once with a real parent. The differentiators vs the (single-firing) react path are:
1. enrich_config_with_node_metadata replaces config["callbacks"] with a flat LIST,
   severing the inherited CallbackManager identity, and
2. the runnable consumed via astream_events is a RunnableBinding (bind_tools).

This reproduction runs inside a real LangGraph Pregel graph (prod stream modes) so the
graph-level handler is propagated by the Pregel contextvar — the third ingredient that
RunnableLambda does not reproduce.
"""

from __future__ import annotations

from collections import defaultdict
from typing import Any
from uuid import UUID

import pytest
from langchain_core.callbacks import AsyncCallbackHandler
from langchain_core.language_models.fake_chat_models import GenericFakeChatModel
from langchain_core.messages import AIMessage, HumanMessage
from langchain_core.runnables import RunnableConfig
from langgraph.graph import END, START, StateGraph
from typing_extensions import TypedDict


class _CountingHandler(AsyncCallbackHandler):
    def __init__(self) -> None:
        self.fires: dict[str, list[str | None]] = defaultdict(list)

    async def on_llm_end(
        self, response: Any, *, run_id: UUID, parent_run_id: UUID | None = None, **kwargs: Any
    ) -> None:
        self.fires[str(run_id)].append(str(parent_run_id) if parent_run_id else None)


class _S(TypedDict):
    messages: list


_PROD_MODES = ["values", "messages", "updates", "custom"]


async def _run_in_graph(node_body) -> _CountingHandler:
    counter = _CountingHandler()
    model = GenericFakeChatModel(messages=iter([AIMessage(content="hi")] * 100))

    async def node(state: _S, config: RunnableConfig) -> dict:
        await node_body(model, config)
        return {}

    g = StateGraph(_S)
    g.add_node("n", node)
    g.add_edge(START, "n")
    g.add_edge("n", END)
    app = g.compile()
    async for _ in app.astream(
        {"messages": [HumanMessage(content="q")]},
        {"callbacks": [counter]},
        stream_mode=_PROD_MODES,
    ):
        pass
    return counter


async def _flat_list_config_on_binding(model: Any, config: RunnableConfig) -> None:
    """Reproduces initiative: enrich (flat list) + astream_events over a binding."""
    from src.infrastructure.llm.invoke_helpers import enrich_config_with_node_metadata
    from src.infrastructure.llm.reasoning_stream import stream_reasoning_events

    enriched = enrich_config_with_node_metadata(config, "initiative")
    bound = model.bind(stop=None)  # RunnableBinding, like bind_tools(...)
    await stream_reasoning_events(
        bound, [HumanMessage(content="q")], emit=lambda _t: None, config=enriched
    )


async def _manager_config_on_binding(model: Any, config: RunnableConfig) -> None:
    """Reproduces react: raw config (CallbackManager preserved) + binding."""
    from src.infrastructure.llm.reasoning_stream import stream_reasoning_events

    bound = model.bind(stop=None)
    await stream_reasoning_events(
        bound, [HumanMessage(content="q")], emit=lambda _t: None, config=config
    )


async def _preserving_enrich_on_binding(model: Any, config: RunnableConfig) -> None:
    """The FIX: enrich while preserving the CallbackManager + astream_events over a binding."""
    from src.infrastructure.llm.invoke_helpers import enrich_config_preserving_callbacks
    from src.infrastructure.llm.reasoning_stream import stream_reasoning_events

    enriched = enrich_config_preserving_callbacks(config, "initiative")
    bound = model.bind(stop=None)
    await stream_reasoning_events(
        bound, [HumanMessage(content="q")], emit=lambda _t: None, config=enriched
    )


@pytest.mark.asyncio
async def test_flat_list_config_double_fires() -> None:
    """Characterization: flat-list enrich + binding + astream_events double-fires.

    This documents *why* ``enrich_config_preserving_callbacks`` is required (it is not
    cargo-cult). If this test ever fails (no longer doubles), the underlying
    LangChain/LangGraph callback-propagation behaviour has changed — re-evaluate
    whether the manager-preserving workaround is still needed, do not silently relax it.
    """
    counter = await _run_in_graph(_flat_list_config_on_binding)
    print("FLAT-LIST fires:", dict(counter.fires))
    assert counter.fires
    # The bug: at least one run_id is fired twice (both with parent_run_id=None).
    assert any(len(v) == 2 for v in counter.fires.values()), dict(counter.fires)


@pytest.mark.asyncio
async def test_preserving_enrich_fires_once() -> None:
    """The FIX: preserving the CallbackManager keeps a single firing per LLM run_id."""
    counter = await _run_in_graph(_preserving_enrich_on_binding)
    print("PRESERVING fires:", dict(counter.fires))
    assert counter.fires
    assert all(len(v) == 1 for v in counter.fires.values()), dict(counter.fires)


@pytest.mark.asyncio
async def test_manager_config_fires_once() -> None:
    counter = await _run_in_graph(_manager_config_on_binding)
    print("MANAGER fires:", dict(counter.fires))
    assert counter.fires
    assert all(len(v) == 1 for v in counter.fires.values()), dict(counter.fires)
