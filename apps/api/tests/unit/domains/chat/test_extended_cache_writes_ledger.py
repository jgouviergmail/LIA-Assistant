"""A one-hour cache write reaches the turn's ledger at its own rate (ADR-362).

The streamed shape the Claude hooks produce (the write total from the stream's
end, its lifetime split from its start) goes through the two callbacks a turn
attaches, exactly as a ReAct model call does: the ledger's record, its log row
and the metrics must all carry the split, and the price must be the vendor's.
"""

from __future__ import annotations

from unittest.mock import patch
from uuid import uuid4

import pytest
from langchain_core.messages import AIMessage
from langchain_core.outputs import ChatGeneration, LLMResult

from src.domains.chat.service import TrackingContext
from src.domains.chat.tracking_records import token_log_row
from src.infrastructure.cache import pricing_cache
from src.infrastructure.cache.pricing_cache import CachedModelPrice, PricingCacheData
from src.infrastructure.llm.usage_metadata import (
    STREAM_CACHE_WRITE_EXTENDED_KEY,
    STREAM_CACHE_WRITE_SHORT_KEY,
)
from src.infrastructure.observability.callbacks import MetricsCallbackHandler, TokenTrackingCallback

pytestmark = pytest.mark.unit

MODEL = "claude-extended-test"
INPUT, OUTPUT, CACHED = 4.0, 20.0, 0.2


@pytest.fixture(autouse=True)
def _claude_tariff(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        pricing_cache,
        "_local_cache",
        PricingCacheData(
            models={
                MODEL: CachedModelPrice(
                    input_unit_price=INPUT,
                    output_unit_price=OUTPUT,
                    cached_input_unit_price=CACHED,
                    cache_write_multiplier=1.25,
                    cache_write_extended_multiplier=2.0,
                )
            },
            usd_eur_rate=0.9,
            last_refresh_ts=0,
        ),
    )


def _streamed_result() -> LLMResult:
    """10,000 prompt tokens: 2,000 read, 5,000 written (3,800 for the hour)."""
    message = AIMessage(
        content="done",
        response_metadata={"model_name": MODEL},
        usage_metadata={
            "input_tokens": 10_000,
            "output_tokens": 100,
            "total_tokens": 10_100,
            "input_token_details": {
                "cache_read": 2_000,
                "cache_creation": 5_000,
                STREAM_CACHE_WRITE_SHORT_KEY: 1_200,
                STREAM_CACHE_WRITE_EXTENDED_KEY: 3_800,
            },
        },
    )
    return LLMResult(generations=[[ChatGeneration(message=message)]])


#: 8,000 billable prompt tokens at 4, 100 output at 20, 2,000 read at 0.2, and
#: the surcharges: 1,200 short writes at 0.25x, 3,800 extended ones at 1x.
EXPECTED_USD = (
    8_000 * INPUT + 100 * OUTPUT + 2_000 * CACHED + INPUT * (1_200 * 0.25 + 3_800)
) / 1e6


async def test_the_ledger_and_the_metrics_price_the_hour_at_its_rate() -> None:
    run_id = str(uuid4())
    tracker = TrackingContext(run_id, uuid4(), "session", uuid4(), auto_commit=False)
    callback = TokenTrackingCallback(tracker, run_id=run_id)
    metrics = MetricsCallbackHandler(node_name="react_call_model")
    llm_run = uuid4()
    with (
        patch("src.infrastructure.observability.callbacks.llm_cost_total") as cost_metric,
        patch("src.infrastructure.observability.callbacks.llm_cache_write_tokens_total") as writes,
    ):
        await callback.on_chat_model_start(
            {}, [[]], run_id=llm_run, metadata={"langgraph_node": "react_call_model"}
        )
        await metrics.on_chat_model_start({}, [[]], run_id=llm_run)
        await callback.on_llm_end(_streamed_result(), run_id=llm_run)
        await metrics.on_llm_end(_streamed_result(), run_id=llm_run)

    try:
        record = tracker._node_records[0]
        assert record.cost_usd == pytest.approx(EXPECTED_USD)
        assert (record.cache_write_tokens, record.cache_write_extended_tokens) == (5_000, 3_800)
        row = token_log_row(record)
        assert (row["cache_write_tokens"], row["cache_write_extended_tokens"]) == (5_000, 3_800)
        # The metrics door prices the same call the same way, in EUR here.
        cost_metric.labels.return_value.inc.assert_called_once()
        increments = {
            call.kwargs["lifetime"]: inc.args[0]
            for call, inc in zip(
                writes.labels.call_args_list,
                writes.labels.return_value.inc.call_args_list,
                strict=True,
            )
        }
        assert increments == {"short": 1_200, "extended": 3_800}
    finally:
        tracker.cleanup_run_records(run_id)


async def test_a_background_caller_that_reports_no_split_is_priced_short() -> None:
    """``record_node_tokens`` defaults the extended part to 0: every other door
    prices its writes at the short rate, as before (no extended writer exists
    outside the ReAct model call)."""
    run_id = str(uuid4())
    tracker = TrackingContext(run_id, uuid4(), "session", uuid4(), auto_commit=False)
    try:
        await tracker.record_node_tokens(
            "memory_extraction", MODEL, 1_000_000, 0, 0, cache_write_tokens=1_000_000
        )
        record = tracker._node_records[0]
        assert record.cost_usd == pytest.approx(INPUT * 1.25)
        assert (record.cache_write_tokens, record.cache_write_extended_tokens) == (1_000_000, 0)
    finally:
        tracker.cleanup_run_records(run_id)
