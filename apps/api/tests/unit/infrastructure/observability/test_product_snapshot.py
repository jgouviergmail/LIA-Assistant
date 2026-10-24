"""A disappearing cohort must not leave yesterday's ratio in multiprocess metrics."""

import math
import warnings
from contextlib import asynccontextmanager
from unittest.mock import AsyncMock

import pytest

from src.infrastructure.observability import metrics_product as metrics

pytestmark = pytest.mark.unit


async def test_refresh_replaces_missing_series_without_unsupported_clear(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from src.domains.product import repository
    from src.infrastructure import database

    repo = AsyncMock()
    repo.count_useful_users.return_value = 2
    repo.penetration_by_device.return_value = {"desktop": 0.5, "all": 0.5}
    repo.activation_rate.return_value = 0.5
    repo.retention_rate.return_value = 0.5
    repo.funnel_counts.return_value = {"registered": 4}
    repo.data_quality_ratios.return_value = {"outcomes_with_domain": 0.5}
    repo.validated_outcome_value.return_value = (None, None)

    @asynccontextmanager
    async def db():
        yield object()

    monkeypatch.setattr(database, "get_db_context", db)
    monkeypatch.setattr(repository, "ProductRepository", lambda session: repo)
    # prometheus_client warns on clear even when the families were imported
    # before multiprocess was armed. This catches the deployed warning too.
    monkeypatch.setenv("PROMETHEUS_MULTIPROC_DIR", "unused")
    with warnings.catch_warnings():
        warnings.simplefilter("error", UserWarning)
        await metrics.refresh_product_gauges()
        assert metrics.product_value_penetration_ratio.labels("7d", "desktop")._value.get() == 0.5
        repo.penetration_by_device.return_value = {}
        repo.activation_rate.return_value = None
        repo.retention_rate.return_value = None
        repo.funnel_counts.return_value = {}
        repo.data_quality_ratios.return_value = {}
        await metrics.refresh_product_gauges()
    assert math.isnan(metrics.product_value_penetration_ratio.labels("7d", "desktop")._value.get())
    assert math.isnan(metrics.product_activation_rate.labels("7d", "all", "all")._value.get())
    assert metrics.product_funnel_users.labels("registered", "7d", "all")._value.get() == 0

    stamp = metrics.product_metrics_last_refresh_timestamp_seconds.labels(
        "product_rollup"
    )._value.get()
    # Failure after a query succeeded must not publish a partial snapshot.
    repo.count_useful_users.side_effect = [99, RuntimeError("database unavailable")]
    with pytest.raises(RuntimeError):
        await metrics.refresh_product_gauges()
    assert (
        metrics.product_users_with_useful_outcome.labels(
            "7d", metrics.USEFUL_EVIDENCE_SELECTORS[0]
        )._value.get()
        == 2
    )
    assert (
        metrics.product_metrics_last_refresh_timestamp_seconds.labels("product_rollup")._value.get()
        == stamp
    )


async def test_refresh_publishes_the_cost_and_latency_of_validated_outcomes(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """AC-006: the product value panels read gauges the rollup computes in PostgreSQL."""
    from src.domains.product import repository
    from src.infrastructure import database

    repo = AsyncMock()
    repo.count_useful_users.return_value = 0
    repo.penetration_by_device.return_value = {}
    repo.activation_rate.return_value = None
    repo.retention_rate.return_value = None
    repo.funnel_counts.return_value = {}
    repo.data_quality_ratios.return_value = {}
    repo.validated_outcome_value.side_effect = lambda days: (
        (0.0125, 4.5) if days == 7 else (None, None)
    )

    @asynccontextmanager
    async def db():
        yield object()

    monkeypatch.setattr(database, "get_db_context", db)
    monkeypatch.setattr(repository, "ProductRepository", lambda session: repo)

    await metrics.refresh_product_gauges()

    assert metrics.product_outcome_cost_eur_mean.labels("7d")._value.get() == 0.0125
    assert metrics.product_outcome_latency_p50_seconds.labels("7d")._value.get() == 4.5
    # No outcome validated in the window: no denominator, never a measured zero.
    assert math.isnan(metrics.product_outcome_cost_eur_mean.labels("30d")._value.get())
    assert math.isnan(metrics.product_outcome_latency_p50_seconds.labels("30d")._value.get())
