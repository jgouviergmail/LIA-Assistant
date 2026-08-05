"""Unit tests for TrackingContext started_offset_ms (debug-panel waterfall).

The debug panel's LLM waterfall needs each call's START position on the
run's timeline, not just its duration. The offset is anchored on a
RUN-LEVEL t0 shared by every TrackingContext of the run (pipeline +
background tasks), because per-context anchors would break cross-context
chronology — the exact defect the per-context ``sequence`` counter has.
"""

from decimal import Decimal
from unittest.mock import patch
from uuid import uuid4

import pytest

from src.domains.chat.service import TokenUsageRecord, TrackingContext


def _ctx(run_id: str) -> TrackingContext:
    ctx = TrackingContext(
        run_id=run_id,
        user_id=uuid4(),
        session_id="test-session",
        conversation_id=uuid4(),
        auto_commit=False,
    )
    ctx._context_token = None  # Skip ContextVar setup
    return ctx


async def _record(ctx: TrackingContext, **kwargs) -> None:
    defaults = {
        "node_name": "router",
        "model_name": "m",
        "prompt_tokens": 10,
        "completion_tokens": 5,
        "cached_tokens": 0,
        "cost_usd": 0.01,
        "cost_eur": 0.009,
        "usd_to_eur_rate": Decimal("0.92"),
    }
    defaults.update(kwargs)
    await ctx.record_node_tokens(**defaults)


def test_token_usage_record_default_offset_is_zero() -> None:
    record = TokenUsageRecord(
        node_name="router",
        model_name="m",
        prompt_tokens=1,
        completion_tokens=1,
        cached_tokens=0,
        cost_usd=0.0,
        cost_eur=0.0,
        usd_to_eur_rate=Decimal("0.92"),
    )
    assert record.started_offset_ms == 0.0


async def test_explicit_started_at_measured_from_run_start() -> None:
    run_id = f"offset-{uuid4()}"
    with patch("src.domains.chat.run_records.time") as mock_time:
        mock_time.time.return_value = 1000.0
        ctx = _ctx(run_id)  # anchors the run t0 at 1000.0
        await _record(ctx, started_at=1001.5, duration_ms=200.0)

    try:
        breakdown = ctx.get_llm_calls_breakdown()
        assert breakdown[0]["started_offset_ms"] == pytest.approx(1500.0)
    finally:
        TrackingContext.cleanup_run_records(run_id)


async def test_missing_started_at_derives_offset_from_now_minus_duration() -> None:
    run_id = f"offset-{uuid4()}"
    now = {"t": 1000.0}
    with patch("src.domains.chat.run_records.time") as mock_time:
        mock_time.time.side_effect = lambda: now["t"]
        ctx = _ctx(run_id)  # t0 = 1000.0
        now["t"] = 1002.0
        await _record(ctx, duration_ms=200.0)

    try:
        breakdown = ctx.get_llm_calls_breakdown()
        # (1002.0 - 1000.0) * 1000 - 200 = 1800.0
        assert breakdown[0]["started_offset_ms"] == pytest.approx(1800.0)
    finally:
        TrackingContext.cleanup_run_records(run_id)


async def test_started_at_before_run_t0_clamps_to_zero() -> None:
    run_id = f"offset-{uuid4()}"
    with patch("src.domains.chat.run_records.time") as mock_time:
        mock_time.time.return_value = 1000.0
        ctx = _ctx(run_id)
        await _record(ctx, started_at=999.0, duration_ms=50.0)

    try:
        assert ctx.get_llm_calls_breakdown()[0]["started_offset_ms"] == 0.0
    finally:
        TrackingContext.cleanup_run_records(run_id)


async def test_second_context_shares_the_run_anchor() -> None:
    """A background-task context created later measures from the FIRST t0."""
    run_id = f"offset-{uuid4()}"
    now = {"t": 1000.0}
    with patch("src.domains.chat.run_records.time") as mock_time:
        mock_time.time.side_effect = lambda: now["t"]
        _ctx(run_id)  # pipeline context anchors t0 = 1000.0
        now["t"] = 1004.0
        background = _ctx(run_id)  # must NOT re-anchor
        await _record(background, started_at=1005.0, duration_ms=10.0)

    try:
        breakdown = background.get_llm_calls_breakdown()
        assert breakdown[0]["started_offset_ms"] == pytest.approx(5000.0)
    finally:
        TrackingContext.cleanup_run_records(run_id)


async def test_cleanup_releases_the_run_anchor() -> None:
    run_id = f"offset-{uuid4()}"
    with patch("src.domains.chat.run_records.time") as mock_time:
        mock_time.time.return_value = 1000.0
        _ctx(run_id)
    TrackingContext.cleanup_run_records(run_id)

    with patch("src.domains.chat.run_records.time") as mock_time:
        mock_time.time.return_value = 2000.0
        ctx = _ctx(run_id)  # fresh anchor after cleanup
        await _record(ctx, started_at=2001.0, duration_ms=10.0)

    try:
        assert ctx.get_llm_calls_breakdown()[0]["started_offset_ms"] == pytest.approx(1000.0)
    finally:
        TrackingContext.cleanup_run_records(run_id)
