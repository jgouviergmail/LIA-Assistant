"""A paid LLM call that returns no usage must produce an exploitable signal.

Before ADR-220 the only trace of a streamed call completing without token
usage was a ``model="unknown"`` label on ``llm_api_calls_total`` and a DEBUG
log — invisible on every dashboard and in every log level shipped to
production. That silence is what let the deepseek branch omit the usage ask
for months (ex-F1): accounting kept working only because the provider sent
usage unrequested.

What must hold:
- ``MetricsCallbackHandler.on_llm_end`` on a usage-less result increments
  ``llm_calls_without_usage_total{node_name}`` exactly once and logs a
  WARNING (node_name only — never message content, PII rule);
- ``TokenTrackingCallback`` logs its ``token_tracking_no_usage`` at WARNING
  (it does NOT increment the counter: both handlers fire for the same call,
  a second increment would double-count);
- a result WITH usage increments nothing.
"""

from __future__ import annotations

from typing import Any
from unittest.mock import AsyncMock
from uuid import uuid4

from langchain_core.messages import AIMessage
from langchain_core.outputs import ChatGeneration, LLMResult

from src.infrastructure.observability.callbacks import (
    MetricsCallbackHandler,
    TokenTrackingCallback,
    llm_calls_without_usage_total,
)


def _result(with_usage: bool) -> LLMResult:
    """A minimal LLMResult, with or without usage metadata."""
    usage: dict[str, Any] | None = (
        {"input_tokens": 10, "output_tokens": 5, "total_tokens": 15} if with_usage else None
    )
    message = AIMessage(content="ok", usage_metadata=usage)  # type: ignore[arg-type]
    if with_usage:
        message.response_metadata = {"model_name": "test-model"}
    return LLMResult(generations=[[ChatGeneration(message=message)]])


def _counter_value(node_name: str) -> float:
    return llm_calls_without_usage_total.labels(node_name=node_name)._value.get()


class TestMetricsHandlerWithoutUsage:
    async def test_usage_less_call_increments_counter_and_warns(self, caplog) -> None:
        handler = MetricsCallbackHandler(node_name="response")
        before = _counter_value("response")

        with caplog.at_level("WARNING"):
            await handler.on_llm_end(_result(with_usage=False), run_id=uuid4())

        assert _counter_value("response") == before + 1
        assert any("llm_call_without_usage" in r.message for r in caplog.records)

    async def test_duplicate_end_counts_once(self) -> None:
        handler = MetricsCallbackHandler(node_name="response")
        before = _counter_value("response")
        run_id = uuid4()

        await handler.on_llm_end(_result(with_usage=False), run_id=run_id)
        await handler.on_llm_end(_result(with_usage=False), run_id=run_id)

        assert _counter_value("response") == before + 1

    async def test_call_with_usage_increments_nothing(self) -> None:
        handler = MetricsCallbackHandler(node_name="response")
        before = _counter_value("response")

        await handler.on_llm_end(_result(with_usage=True), run_id=uuid4())

        assert _counter_value("response") == before


class TestTokenTrackingWithoutUsage:
    async def test_no_usage_logs_warning_without_counter(self, caplog) -> None:
        """The tracking side warns too, but never double-counts the metric."""
        tracker = AsyncMock()
        handler = TokenTrackingCallback(tracker, "run-1")
        before = _counter_value("unknown")

        with caplog.at_level("WARNING"):
            await handler.on_llm_end(_result(with_usage=False), run_id=uuid4())

        assert any("token_tracking_no_usage" in r.message for r in caplog.records)
        assert _counter_value("unknown") == before
        tracker.record_node_tokens.assert_not_awaited()
