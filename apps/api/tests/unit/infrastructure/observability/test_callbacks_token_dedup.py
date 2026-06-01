"""Unit tests for TokenTrackingCallback idempotency on duplicate ``on_llm_end``.

A single physical LLM call must be recorded exactly once, even when its
``on_llm_end`` fires twice for the same LLM ``run_id``. This happens on the
reasoning-streaming path (``astream_events``) when the handler is attached both
as an inherited (graph-level) handler and as a local (per-node, post-``enrich``)
handler: LangChain does not dedupe the two attachments under ``astream_events``,
so the callback's ``on_llm_end`` is invoked twice for the same run.

Without the guard, the second invocation finds the per-call context already
popped and records a phantom ``node_name="unknown"`` row with identical tokens —
double-counting the call in the debug panel, the persisted ``MessageTokenSummary``
total, ``token_usage_logs`` and ``user_statistics``.
"""

from unittest.mock import patch
from uuid import uuid4

import pytest
from langchain_core.messages import AIMessage
from langchain_core.outputs import ChatGeneration, LLMResult

from src.domains.chat.service import TrackingContext
from src.infrastructure.observability.callbacks import (
    MetricsCallbackHandler,
    TokenTrackingCallback,
)


def _make_llm_result(input_tokens: int, output_tokens: int, model: str) -> LLMResult:
    """Build an LLMResult parseable by TokenExtractor (modern usage_metadata path)."""
    message = AIMessage(
        content="ok",
        usage_metadata={
            "input_tokens": input_tokens,
            "output_tokens": output_tokens,
            "total_tokens": input_tokens + output_tokens,
        },
        response_metadata={"model_name": model},
    )
    return LLMResult(generations=[[ChatGeneration(message=message)]])


def _make_tracker() -> TrackingContext:
    """Create a TrackingContext that records in-memory without DB/ContextVar setup."""
    ctx = TrackingContext(
        run_id="graph-run",
        user_id=uuid4(),
        session_id="sess",
        conversation_id=uuid4(),
        auto_commit=False,
    )
    ctx._context_token = None  # Skip ContextVar teardown
    return ctx


@pytest.mark.asyncio
async def test_duplicate_on_llm_end_same_run_id_records_once() -> None:
    """Two on_llm_end for the same LLM run_id record a single, correctly-named row."""
    tracker = _make_tracker()
    callback = TokenTrackingCallback(tracker, run_id="graph-run")
    llm_run_id = uuid4()

    await callback.on_chat_model_start(
        {}, [[]], run_id=llm_run_id, metadata={"langgraph_node": "initiative"}
    )
    result = _make_llm_result(1871, 357, "gpt-5.2-2025-12-11")

    with (
        patch(
            "src.infrastructure.cache.pricing_cache.get_cached_cost_usd_eur",
            return_value=(0.01, 0.009),
        ),
        patch(
            "src.infrastructure.cache.pricing_cache.get_cached_usd_eur_rate",
            return_value=0.92,
        ),
    ):
        await callback.on_llm_end(result, run_id=llm_run_id)
        await callback.on_llm_end(result, run_id=llm_run_id)  # duplicate (double-attached)

    assert len(tracker._node_records) == 1, "Duplicate on_llm_end must not double-count"
    assert tracker._node_records[0].node_name == "initiative"
    assert tracker._node_records[0].prompt_tokens == 1871
    assert tracker._node_records[0].completion_tokens == 357


@pytest.mark.asyncio
async def test_distinct_run_ids_each_record() -> None:
    """Genuinely distinct LLM calls (distinct run_ids) are each recorded."""
    tracker = _make_tracker()
    callback = TokenTrackingCallback(tracker, run_id="graph-run")
    run_a, run_b = uuid4(), uuid4()

    await callback.on_chat_model_start(
        {}, [[]], run_id=run_a, metadata={"langgraph_node": "planner"}
    )
    await callback.on_chat_model_start(
        {}, [[]], run_id=run_b, metadata={"langgraph_node": "response"}
    )

    with (
        patch(
            "src.infrastructure.cache.pricing_cache.get_cached_cost_usd_eur",
            return_value=(0.01, 0.009),
        ),
        patch(
            "src.infrastructure.cache.pricing_cache.get_cached_usd_eur_rate",
            return_value=0.92,
        ),
    ):
        await callback.on_llm_end(_make_llm_result(100, 50, "m"), run_id=run_a)
        await callback.on_llm_end(_make_llm_result(200, 80, "m"), run_id=run_b)

    assert len(tracker._node_records) == 2
    assert {r.node_name for r in tracker._node_records} == {"planner", "response"}


# ============================================================================
# MetricsCallbackHandler (Prometheus) — symmetric idempotency guard
# ============================================================================


@pytest.mark.asyncio
async def test_metrics_duplicate_on_llm_end_emits_once() -> None:
    """Two on_llm_end for the same run_id emit Prometheus metrics only once.

    Symmetric defense-in-depth to TokenTrackingCallback: the metrics path
    (llm_api_calls_total / llm_tokens_consumed_total / llm_api_latency_seconds)
    must not double-count if a duplicate on_llm_end reaches the same instance.
    """
    handler = MetricsCallbackHandler(node_name="initiative", llm=None)
    llm_run_id = uuid4()
    await handler.on_chat_model_start({}, [[]], run_id=llm_run_id)
    result = _make_llm_result(1871, 357, "gpt-5.2-2025-12-11")

    with (
        patch("src.infrastructure.observability.callbacks.llm_api_calls_total") as m_calls,
        patch("src.infrastructure.observability.callbacks.llm_tokens_consumed_total") as m_tokens,
        patch("src.infrastructure.observability.callbacks.llm_api_latency_seconds") as m_latency,
    ):
        await handler.on_llm_end(result, run_id=llm_run_id)
        await handler.on_llm_end(result, run_id=llm_run_id)  # duplicate (double-attached)

    # Success counter incremented exactly once, not twice.
    assert m_calls.labels.return_value.inc.call_count == 1
    # Tokens (prompt + completion) emitted once each — never doubled.
    assert m_tokens.labels.return_value.inc.call_count == 2
    assert m_latency.labels.return_value.observe.call_count == 1


@pytest.mark.asyncio
async def test_metrics_distinct_run_ids_each_emit() -> None:
    """Genuinely distinct LLM calls each emit their own metrics (no over-dedup)."""
    handler = MetricsCallbackHandler(node_name="planner", llm=None)
    run_a, run_b = uuid4(), uuid4()
    await handler.on_chat_model_start({}, [[]], run_id=run_a)
    await handler.on_chat_model_start({}, [[]], run_id=run_b)

    with (
        patch("src.infrastructure.observability.callbacks.llm_api_calls_total") as m_calls,
        patch("src.infrastructure.observability.callbacks.llm_tokens_consumed_total"),
        patch("src.infrastructure.observability.callbacks.llm_api_latency_seconds"),
    ):
        await handler.on_llm_end(_make_llm_result(100, 50, "m"), run_id=run_a)
        await handler.on_llm_end(_make_llm_result(200, 80, "m"), run_id=run_b)

    assert m_calls.labels.return_value.inc.call_count == 2


@pytest.mark.asyncio
async def test_metrics_duplicate_no_usage_path_guarded() -> None:
    """The no-usage branch is also guarded — duplicate fires emit a single api_call."""
    handler = MetricsCallbackHandler(node_name="initiative", llm=None)
    llm_run_id = uuid4()
    await handler.on_chat_model_start({}, [[]], run_id=llm_run_id)
    empty = LLMResult(generations=[[ChatGeneration(message=AIMessage(content="ok"))]])

    with (
        patch("src.infrastructure.observability.callbacks.llm_api_calls_total") as m_calls,
        patch("src.infrastructure.observability.callbacks.llm_api_latency_seconds") as m_latency,
    ):
        await handler.on_llm_end(empty, run_id=llm_run_id)
        await handler.on_llm_end(empty, run_id=llm_run_id)  # duplicate

    assert m_calls.labels.return_value.inc.call_count == 1
    assert m_latency.labels.return_value.observe.call_count == 1
