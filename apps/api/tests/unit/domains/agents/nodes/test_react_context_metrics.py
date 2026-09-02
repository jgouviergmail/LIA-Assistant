"""Delivered-context measurement for the ReAct loop (Lot D, 2026-09).

The loop's iteration count and duration were measured; the thing that actually
grows — the prompt DELIVERED to the model at each iteration — was not
(quadratic cumulative growth measured 2026-09-02: 2.3k tokens delivered at
iteration 1, 112k at iteration 90). These tests pin the instrumentation:

- ``count_messages_tokens_cached`` (models.py) is the ONE memoized counter —
  the same per-message-id cache the reducer uses, so the hot path never
  re-encodes an unchanged ToolMessage;
- ``react_call_model_node`` observes ``react_delivered_context_tokens`` and
  ``react_context_window_utilization`` on every call, and a metric failure can
  never break the loop.
"""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest
from langchain_core.messages import AIMessage, HumanMessage, ToolMessage
from prometheus_client import REGISTRY

pytestmark = [pytest.mark.unit]


def _sample(name: str, suffix: str) -> float:
    value = REGISTRY.get_sample_value(f"{name}{suffix}")
    return 0.0 if value is None else value


# ============================================================================
# The memoized counter export
# ============================================================================


class TestCountMessagesTokensCached:
    def test_counts_string_content(self) -> None:
        from src.domains.agents.models import count_messages_tokens_cached

        messages = [
            HumanMessage(content="Prepare my day please.", id="h1"),
            AIMessage(content="On it.", id="a1"),
        ]
        total = count_messages_tokens_cached(messages)
        assert total > 0
        # Deterministic across calls (cache hit path returns the same count).
        assert count_messages_tokens_cached(messages) == total

    def test_empty_list_is_zero(self) -> None:
        from src.domains.agents.models import count_messages_tokens_cached

        assert count_messages_tokens_cached([]) == 0


# ============================================================================
# Node-level observation
# ============================================================================


@pytest.fixture
def react_state() -> dict:
    return {
        "messages": [
            HumanMessage(content="Check my emails.", id="h1"),
            AIMessage(
                content="",
                id="a1",
                tool_calls=[{"name": "t", "args": {}, "id": "c1"}],
            ),
            ToolMessage(content="Retrieved 3 emails.", id="t1", tool_call_id="c1", name="t"),
        ],
        "react_tool_names": [],
        "react_hitl_map": {},
        "react_iteration": 1,
        "react_system_blocks": ["You are LIA."],
        "react_elapsed_seconds": 0.0,
    }


async def test_call_model_observes_delivered_context(
    monkeypatch: pytest.MonkeyPatch, react_state: dict
) -> None:
    import src.domains.agents.nodes.react_nodes as rn

    monkeypatch.setattr(rn, "get_llm", lambda *_a, **_k: MagicMock())
    monkeypatch.setattr(rn, "_rebuild_wrapped_tools", lambda *_a, **_k: [])

    async def fake_stream(_llm, _messages, emit, config):  # noqa: ANN001
        return AIMessage(content="done", id="out1")

    monkeypatch.setattr(
        "src.infrastructure.llm.reasoning_stream.stream_reasoning_events", fake_stream
    )

    before_count = _sample("react_delivered_context_tokens", "_count")
    before_sum = _sample("react_delivered_context_tokens", "_sum")

    result = await rn.react_call_model_node(react_state, config={})

    assert result["messages"][0].content == "done"
    assert _sample("react_delivered_context_tokens", "_count") == before_count + 1
    # The observed value is the real prompt size: strictly positive.
    assert _sample("react_delivered_context_tokens", "_sum") > before_sum


async def test_call_model_observes_window_utilization(
    monkeypatch: pytest.MonkeyPatch, react_state: dict
) -> None:
    import src.domains.agents.nodes.react_nodes as rn

    monkeypatch.setattr(rn, "get_llm", lambda *_a, **_k: MagicMock())
    monkeypatch.setattr(rn, "_rebuild_wrapped_tools", lambda *_a, **_k: [])

    async def fake_stream(_llm, _messages, emit, config):  # noqa: ANN001
        return AIMessage(content="done", id="out1")

    monkeypatch.setattr(
        "src.infrastructure.llm.reasoning_stream.stream_reasoning_events", fake_stream
    )

    before = _sample("react_context_window_utilization", "_count")
    await rn.react_call_model_node(react_state, config={})
    after = _sample("react_context_window_utilization", "_count")
    assert after == before + 1
    # A tiny prompt against a real window: the ratio lands in the lowest bucket.
    low_bucket = REGISTRY.get_sample_value(
        "react_context_window_utilization_bucket", {"le": "0.25"}
    )
    assert low_bucket is not None and low_bucket >= after


async def test_metric_failure_never_breaks_the_loop(
    monkeypatch: pytest.MonkeyPatch, react_state: dict
) -> None:
    """Observability is best-effort: a counting failure must not kill the turn."""
    import src.domains.agents.nodes.react_nodes as rn

    monkeypatch.setattr(rn, "get_llm", lambda *_a, **_k: MagicMock())
    monkeypatch.setattr(rn, "_rebuild_wrapped_tools", lambda *_a, **_k: [])

    async def fake_stream(_llm, _messages, emit, config):  # noqa: ANN001
        return AIMessage(content="done", id="out1")

    monkeypatch.setattr(
        "src.infrastructure.llm.reasoning_stream.stream_reasoning_events", fake_stream
    )

    def boom(_messages):  # noqa: ANN001
        raise RuntimeError("tokenizer exploded")

    monkeypatch.setattr(rn, "count_messages_tokens_cached", boom)

    result = await rn.react_call_model_node(react_state, config={})
    assert result["messages"][0].content == "done"
