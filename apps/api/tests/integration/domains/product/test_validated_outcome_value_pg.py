"""The value of a validated outcome, aggregated by PostgreSQL itself (audit AC-006).

The product value panels read two gauges the hourly rollup computes here: the mean
cost and the median request-to-answer latency of the outcomes validated in the
window. ``percentile_cont`` and an average over a ``Numeric`` column are the
server's, so only a real server proves them — and which rows count: still
validated, validated in the window, a missing value skipped rather than read as
zero.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from decimal import Decimal
from uuid import uuid4

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from src.domains.product.models import ProductOutcome
from src.domains.product.repository import ProductRepository

pytestmark = pytest.mark.integration


def _outcome(
    *,
    state: str = "validated",
    validated_days_ago: float | None = 1,
    cost_eur: str | None = None,
    latency_ms: int | None = None,
) -> ProductOutcome:
    now = datetime.now(UTC)
    return ProductOutcome(
        user_id=uuid4(),
        run_id=f"run-{uuid4()}",
        result_type="answer",
        locale="en",
        state=state,
        evidence_level="E1" if state == "validated" else "E3",
        produced_at=now - timedelta(days=10),
        validated_at=(
            None if validated_days_ago is None else now - timedelta(days=validated_days_ago)
        ),
        cost_eur=None if cost_eur is None else Decimal(cost_eur),
        latency_ms=latency_ms,
    )


async def test_the_validated_outcomes_of_the_window_give_their_mean_cost_and_median_latency(
    async_session: AsyncSession,
) -> None:
    async_session.add_all(
        [
            _outcome(cost_eur="0.010000", latency_ms=2_000),
            _outcome(cost_eur="0.030000", latency_ms=4_000),
            _outcome(cost_eur=None, latency_ms=9_000),  # cost not backfilled yet
            _outcome(cost_eur="0.020000", latency_ms=None),  # latency never reported
            # Outside the useful set: produced only, rejected after validation, too old.
            _outcome(state="produced", validated_days_ago=None, cost_eur="9", latency_ms=99_000),
            _outcome(state="rejected", cost_eur="9", latency_ms=99_000),
            _outcome(validated_days_ago=8, cost_eur="9", latency_ms=99_000),
        ]
    )
    await async_session.flush()

    mean_cost, median_latency = await ProductRepository(async_session).validated_outcome_value(7)

    assert mean_cost == pytest.approx(0.02)  # (0.01 + 0.03 + 0.02) / 3
    assert median_latency == pytest.approx(4.0)  # median of 2 s, 4 s, 9 s


async def test_no_validated_outcome_in_the_window_is_no_value_not_a_zero(
    async_session: AsyncSession,
) -> None:
    async_session.add(_outcome(validated_days_ago=40, cost_eur="0.5", latency_ms=1_000))
    await async_session.flush()

    assert await ProductRepository(async_session).validated_outcome_value(30) == (None, None)
