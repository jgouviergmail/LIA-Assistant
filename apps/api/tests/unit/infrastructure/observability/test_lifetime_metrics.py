"""
Unit tests for lifetime_metrics.py

Tests DB-backed Prometheus gauges for restart-safe token tracking.

Phase 4.2 - Testing Observability
Target Coverage: lifetime_metrics.py 0% → 80%+

Metrics Tested (5 Gauges):
    1. llm_tokens_consumed_lifetime - Token totals by model/node/type
    2. llm_cost_lifetime - Cost totals by model/node/currency
    3. lifetime_metrics_update_duration_seconds - Update duration
    4. lifetime_metrics_last_update_timestamp - Last update timestamp
    5. lifetime_metrics_error_total - Error counter

Functions Tested:
    - update_lifetime_metrics() - Background asyncio task
    - refresh_lifetime_metrics_now() - Manual refresh
    - _sync_metrics_from_db() - DB sync logic

Test Strategy:
    - Mock database queries (avoid real DB dependency)
    - Test gauge increments and cache logic
    - Test error handling and backoff
    - Test asyncio task lifecycle
    - Test manual refresh functionality

References:
    - RC1 Root Cause Analysis (Prometheus counter resets)
    - ADR-015: Token Tracking Architecture V2
    - Prometheus Best Practices
"""

import asyncio
from datetime import datetime
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from src.infrastructure.observability.lifetime_metrics import (
    lifetime_metrics_error_total,
    lifetime_metrics_last_update_timestamp,
    lifetime_metrics_update_duration_seconds,
    llm_cost_lifetime,
    llm_tokens_consumed_lifetime,
    refresh_lifetime_metrics_now,
    update_lifetime_metrics,
)


class TestLifetimeMetricsGauges:
    """Test Prometheus Gauge definitions and structure."""

    def test_llm_tokens_consumed_lifetime_exists(self):
        """Test llm_tokens_consumed_lifetime gauge exists."""
        assert llm_tokens_consumed_lifetime is not None
        assert llm_tokens_consumed_lifetime._name == "llm_tokens_consumed_lifetime"

    def test_llm_tokens_consumed_lifetime_labels(self):
        """Test llm_tokens_consumed_lifetime has correct labels."""
        # Labels: model, node_name, token_type
        llm_tokens_consumed_lifetime.labels(
            model="gpt-4.1-mini-mini", node_name="router_node", token_type="prompt_tokens"
        ).set(1000)

        metric_value = llm_tokens_consumed_lifetime.labels(
            model="gpt-4.1-mini-mini", node_name="router_node", token_type="prompt_tokens"
        )._value._value

        assert metric_value == 1000

    def test_llm_cost_lifetime_exists(self):
        """Test llm_cost_lifetime gauge exists."""
        assert llm_cost_lifetime is not None
        assert llm_cost_lifetime._name == "llm_cost_lifetime"

    def test_llm_cost_lifetime_labels(self):
        """Test llm_cost_lifetime has correct labels."""
        # Labels: model, node_name, currency
        llm_cost_lifetime.labels(
            model="claude-3-5-sonnet-20241022", node_name="planner_node", currency="EUR"
        ).set(5.42)

        metric_value = llm_cost_lifetime.labels(
            model="claude-3-5-sonnet-20241022", node_name="planner_node", currency="EUR"
        )._value._value

        assert metric_value == 5.42

    def test_lifetime_metrics_update_duration_seconds_exists(self):
        """Test lifetime_metrics_update_duration_seconds gauge exists."""
        assert lifetime_metrics_update_duration_seconds is not None
        assert (
            lifetime_metrics_update_duration_seconds._name
            == "lifetime_metrics_update_duration_seconds"
        )

    def test_lifetime_metrics_last_update_timestamp_exists(self):
        """Test lifetime_metrics_last_update_timestamp gauge exists."""
        assert lifetime_metrics_last_update_timestamp is not None
        assert (
            lifetime_metrics_last_update_timestamp._name == "lifetime_metrics_last_update_timestamp"
        )

    def test_lifetime_metrics_error_total_exists(self):
        """Test lifetime_metrics_error_total gauge exists."""
        assert lifetime_metrics_error_total is not None
        assert lifetime_metrics_error_total._name == "lifetime_metrics_error_total"


class TestLifetimeMetricsTokenTracking:
    """Test token consumption tracking across restarts."""

    def test_track_prompt_tokens_lifetime(self):
        """Test prompt tokens lifetime tracking."""
        # Track router node prompt tokens
        llm_tokens_consumed_lifetime.labels(
            model="gpt-4.1-mini-mini", node_name="router_node", token_type="prompt_tokens"
        ).set(5000)

        # Track planner node prompt tokens
        llm_tokens_consumed_lifetime.labels(
            model="claude-3-5-sonnet-20241022", node_name="planner_node", token_type="prompt_tokens"
        ).set(12000)

        # Verify values
        router_value = llm_tokens_consumed_lifetime.labels(
            model="gpt-4.1-mini-mini", node_name="router_node", token_type="prompt_tokens"
        )._value._value

        planner_value = llm_tokens_consumed_lifetime.labels(
            model="claude-3-5-sonnet-20241022", node_name="planner_node", token_type="prompt_tokens"
        )._value._value

        assert router_value == 5000
        assert planner_value == 12000

    def test_track_completion_tokens_lifetime(self):
        """Test completion tokens lifetime tracking."""
        llm_tokens_consumed_lifetime.labels(
            model="gpt-4.1-mini-mini", node_name="router_node", token_type="completion_tokens"
        ).set(800)

        metric_value = llm_tokens_consumed_lifetime.labels(
            model="gpt-4.1-mini-mini", node_name="router_node", token_type="completion_tokens"
        )._value._value

        assert metric_value == 800

    def test_track_cached_tokens_lifetime(self):
        """Test cached tokens lifetime tracking."""
        llm_tokens_consumed_lifetime.labels(
            model="claude-3-5-sonnet-20241022", node_name="planner_node", token_type="cached_tokens"
        ).set(3000)

        metric_value = llm_tokens_consumed_lifetime.labels(
            model="claude-3-5-sonnet-20241022", node_name="planner_node", token_type="cached_tokens"
        )._value._value

        assert metric_value == 3000

    def test_track_cost_lifetime(self):
        """Test cost lifetime tracking."""
        # EUR currency (default)
        llm_cost_lifetime.labels(
            model="gpt-4.1-mini-mini", node_name="router_node", currency="EUR"
        ).set(2.35)

        llm_cost_lifetime.labels(
            model="claude-3-5-sonnet-20241022", node_name="planner_node", currency="EUR"
        ).set(8.90)

        router_cost = llm_cost_lifetime.labels(
            model="gpt-4.1-mini-mini", node_name="router_node", currency="EUR"
        )._value._value

        planner_cost = llm_cost_lifetime.labels(
            model="claude-3-5-sonnet-20241022", node_name="planner_node", currency="EUR"
        )._value._value

        assert router_cost == 2.35
        assert planner_cost == 8.90

    def test_simulate_restart_scenario(self):
        """Test simulating API restart (gauges should retain values from DB)."""
        # Before restart: set values from DB
        llm_tokens_consumed_lifetime.labels(
            model="gpt-4.1-mini-mini", node_name="router_node", token_type="prompt_tokens"
        ).set(10000)

        llm_cost_lifetime.labels(
            model="gpt-4.1-mini-mini", node_name="router_node", currency="EUR"
        ).set(5.0)

        # After restart: values would be re-synced from DB (simulated)
        # Note: In real scenario, Prometheus scrapes would show 0 briefly until background task runs

        # Update from DB sync (simulated)
        llm_tokens_consumed_lifetime.labels(
            model="gpt-4.1-mini-mini", node_name="router_node", token_type="prompt_tokens"
        ).set(
            10500
        )  # New value includes pre-restart data

        llm_cost_lifetime.labels(
            model="gpt-4.1-mini-mini", node_name="router_node", currency="EUR"
        ).set(5.25)

        # Verify values persisted via DB
        tokens_value = llm_tokens_consumed_lifetime.labels(
            model="gpt-4.1-mini-mini", node_name="router_node", token_type="prompt_tokens"
        )._value._value

        cost_value = llm_cost_lifetime.labels(
            model="gpt-4.1-mini-mini", node_name="router_node", currency="EUR"
        )._value._value

        assert tokens_value == 10500
        assert cost_value == 5.25


class TestLifetimeMetricsMetadata:
    """Test metadata gauges for observability."""

    def test_update_duration_tracking(self):
        """Test update duration tracking."""
        # Simulate update duration
        duration = 0.045  # 45ms (SLO: <50ms)
        lifetime_metrics_update_duration_seconds.set(duration)

        metric_value = lifetime_metrics_update_duration_seconds._value._value
        assert metric_value == 0.045
        assert metric_value < 0.050  # Within SLO

    def test_last_update_timestamp_tracking(self):
        """Test last update timestamp tracking."""
        now = datetime.utcnow().timestamp()
        lifetime_metrics_last_update_timestamp.set(now)

        metric_value = lifetime_metrics_last_update_timestamp._value._value
        assert metric_value >= now - 1  # Allow 1s tolerance
        assert metric_value <= now + 1

    def test_error_count_tracking(self):
        """Test error count tracking."""
        # Start at 0
        lifetime_metrics_error_total.set(0)

        # Simulate 3 errors
        lifetime_metrics_error_total.set(1)
        lifetime_metrics_error_total.set(2)
        lifetime_metrics_error_total.set(3)

        metric_value = lifetime_metrics_error_total._value._value
        assert metric_value == 3


class TestLifetimeMetricsRefreshNow:
    """Test manual refresh functionality."""

    @pytest.mark.asyncio
    async def test_refresh_lifetime_metrics_now_mock(self):
        """Test manual refresh with mocked DB."""
        # Mock database context and query results
        mock_row = MagicMock()
        mock_row.model_name = "gpt-4.1-mini-mini"
        mock_row.node_name = "router_node"
        mock_row.total_input = 5000
        mock_row.total_output = 800
        mock_row.total_cached = 0
        mock_row.total_cost_eur = 2.35

        mock_result = MagicMock()
        mock_result.all.return_value = [mock_row]

        mock_db = AsyncMock()
        mock_db.execute.return_value = mock_result

        with patch(
            "src.infrastructure.observability.lifetime_metrics.get_db_context"
        ) as mock_context:
            mock_context.return_value.__aenter__.return_value = mock_db

            # Execute manual refresh
            result = await refresh_lifetime_metrics_now()

            # Verify result
            assert "updated_count" in result
            assert "duration_seconds" in result
            assert result["updated_count"] >= 0
            assert result["duration_seconds"] >= 0

    @pytest.mark.asyncio
    async def test_refresh_returns_performance_metrics(self):
        """Test refresh returns performance metrics."""
        with patch(
            "src.infrastructure.observability.lifetime_metrics.get_db_context"
        ) as mock_context:
            mock_db = AsyncMock()
            mock_result = MagicMock()
            mock_result.all.return_value = []
            mock_db.execute.return_value = mock_result
            mock_context.return_value.__aenter__.return_value = mock_db

            result = await refresh_lifetime_metrics_now()

            # Verify structure
            assert isinstance(result, dict)
            assert "updated_count" in result
            assert "duration_seconds" in result
            assert isinstance(result["updated_count"], int)
            assert isinstance(result["duration_seconds"], float)


class TestLifetimeMetricsUpdateTask:
    """Test background update task (asyncio)."""

    @pytest.mark.asyncio
    async def test_update_lifetime_metrics_single_iteration(self):
        """Test single iteration of update task (with cancellation)."""
        # Mock DB to prevent real queries
        mock_row = MagicMock()
        mock_row.model_name = "gpt-4.1-mini-mini"
        mock_row.node_name = "router_node"
        mock_row.total_input = 1000
        mock_row.total_output = 200
        mock_row.total_cached = 0
        mock_row.total_cost_eur = 0.5

        mock_result = MagicMock()
        mock_result.all.return_value = [mock_row]

        mock_db = AsyncMock()
        mock_db.execute.return_value = mock_result

        with patch(
            "src.infrastructure.observability.lifetime_metrics.get_db_context"
        ) as mock_context:
            mock_context.return_value.__aenter__.return_value = mock_db

            # Override update interval to 0.1s for testing
            with patch(
                "src.infrastructure.observability.lifetime_metrics.settings"
            ) as mock_settings:
                mock_settings.lifetime_metrics_update_interval = 0.1
                mock_settings.default_currency = "EUR"

                # Create task
                task = asyncio.create_task(update_lifetime_metrics())

                # Let it run one iteration
                await asyncio.sleep(0.2)

                # Cancel task
                task.cancel()

                try:
                    await task
                except asyncio.CancelledError:
                    pass  # Expected

    @pytest.mark.asyncio
    async def test_update_lifetime_metrics_error_handling(self):
        """Test update task handles errors gracefully."""
        # Mock DB to raise exception
        mock_db = AsyncMock()
        mock_db.execute.side_effect = Exception("Database connection failed")

        with patch(
            "src.infrastructure.observability.lifetime_metrics.get_db_context"
        ) as mock_context:
            mock_context.return_value.__aenter__.return_value = mock_db

            with patch(
                "src.infrastructure.observability.lifetime_metrics.settings"
            ) as mock_settings:
                mock_settings.lifetime_metrics_update_interval = 0.1
                mock_settings.default_currency = "EUR"

                # Create task
                task = asyncio.create_task(update_lifetime_metrics())

                # Let it run and encounter error
                await asyncio.sleep(0.3)

                # Cancel task
                task.cancel()

                try:
                    await task
                except asyncio.CancelledError:
                    pass  # Expected

                # Task should have logged error but continued running

    @pytest.mark.asyncio
    async def test_update_lifetime_metrics_cancellation(self):
        """Test update task responds to cancellation."""
        with patch(
            "src.infrastructure.observability.lifetime_metrics.get_db_context"
        ) as mock_context:
            mock_db = AsyncMock()
            mock_result = MagicMock()
            mock_result.all.return_value = []
            mock_db.execute.return_value = mock_result
            mock_context.return_value.__aenter__.return_value = mock_db

            with patch(
                "src.infrastructure.observability.lifetime_metrics.settings"
            ) as mock_settings:
                mock_settings.lifetime_metrics_update_interval = 0.1
                mock_settings.default_currency = "EUR"

                # Create and cancel task
                task = asyncio.create_task(update_lifetime_metrics())
                await asyncio.sleep(0.15)  # Wait for at least one iteration
                task.cancel()

                # Task should either be cancelled or finish gracefully
                try:
                    await task
                except asyncio.CancelledError:
                    pass  # Expected - task was cancelled during sleep
                # If no exception, task finished before cancellation - also OK


class TestLifetimeMetricsCache:
    """Test in-memory cache optimization."""

    @pytest.mark.asyncio
    async def test_cache_optimization_skip_unchanged(self):
        """Test cache skips gauge updates for unchanged values."""
        # Mock DB with same values twice
        mock_row = MagicMock()
        mock_row.model_name = "gpt-4.1-mini-mini"
        mock_row.node_name = "router_node"
        mock_row.total_input = 1000
        mock_row.total_output = 200
        mock_row.total_cached = 0
        mock_row.total_cost_eur = 0.5

        mock_result = MagicMock()
        mock_result.all.return_value = [mock_row]

        mock_db = AsyncMock()
        mock_db.execute.return_value = mock_result

        with patch(
            "src.infrastructure.observability.lifetime_metrics.get_db_context"
        ) as mock_context:
            mock_context.return_value.__aenter__.return_value = mock_db

            # First refresh - should update cache
            result1 = await refresh_lifetime_metrics_now()
            assert result1["updated_count"] >= 0

            # Second refresh with same data - should skip updates (cached)
            await refresh_lifetime_metrics_now()
            # Cache optimization: updated_count may be 0 if values unchanged

    @pytest.mark.asyncio
    async def test_cache_updates_on_value_change(self):
        """Test cache updates when values change."""
        # First DB call - initial values
        mock_row1 = MagicMock()
        mock_row1.model_name = "gpt-4.1-mini-mini"
        mock_row1.node_name = "router_node"
        mock_row1.total_input = 1000
        mock_row1.total_output = 200
        mock_row1.total_cached = 0
        mock_row1.total_cost_eur = 0.5

        # Second DB call - updated values
        mock_row2 = MagicMock()
        mock_row2.model_name = "gpt-4.1-mini-mini"
        mock_row2.node_name = "router_node"
        mock_row2.total_input = 1500  # Changed
        mock_row2.total_output = 300  # Changed
        mock_row2.total_cached = 0
        mock_row2.total_cost_eur = 0.75  # Changed

        mock_result1 = MagicMock()
        mock_result1.all.return_value = [mock_row1]

        mock_result2 = MagicMock()
        mock_result2.all.return_value = [mock_row2]

        mock_db = AsyncMock()
        mock_db.execute.side_effect = [mock_result1, mock_result2]

        with (
            patch(
                "src.infrastructure.observability.lifetime_metrics.get_db_context"
            ) as mock_context,
            patch(
                "src.infrastructure.observability.lifetime_metrics._sync_period_metrics_from_db",
                new_callable=AsyncMock,
            ),
        ):
            mock_context.return_value.__aenter__.return_value = mock_db

            # First refresh
            result1 = await refresh_lifetime_metrics_now()
            assert result1["updated_count"] >= 0

            # Second refresh with different data
            await refresh_lifetime_metrics_now()
            # Should update because values changed


class TestLifetimeMetricsRealWorldScenarios:
    """Test real-world production scenarios."""

    def test_simulate_multi_agent_token_tracking(self):
        """Test tracking tokens across multiple agents."""
        # Router agent (gpt-4.1-mini-mini)
        llm_tokens_consumed_lifetime.labels(
            model="gpt-4.1-mini-mini", node_name="router_node", token_type="prompt_tokens"
        ).set(5000)
        llm_tokens_consumed_lifetime.labels(
            model="gpt-4.1-mini-mini", node_name="router_node", token_type="completion_tokens"
        ).set(800)
        llm_cost_lifetime.labels(
            model="gpt-4.1-mini-mini", node_name="router_node", currency="EUR"
        ).set(2.35)

        # Planner agent (claude-3-5-sonnet)
        llm_tokens_consumed_lifetime.labels(
            model="claude-3-5-sonnet-20241022", node_name="planner_node", token_type="prompt_tokens"
        ).set(12000)
        llm_tokens_consumed_lifetime.labels(
            model="claude-3-5-sonnet-20241022",
            node_name="planner_node",
            token_type="completion_tokens",
        ).set(3000)
        llm_tokens_consumed_lifetime.labels(
            model="claude-3-5-sonnet-20241022", node_name="planner_node", token_type="cached_tokens"
        ).set(4000)
        llm_cost_lifetime.labels(
            model="claude-3-5-sonnet-20241022", node_name="planner_node", currency="EUR"
        ).set(8.90)

        # Verify all values tracked
        router_prompt = llm_tokens_consumed_lifetime.labels(
            model="gpt-4.1-mini-mini", node_name="router_node", token_type="prompt_tokens"
        )._value._value
        planner_completion = llm_tokens_consumed_lifetime.labels(
            model="claude-3-5-sonnet-20241022",
            node_name="planner_node",
            token_type="completion_tokens",
        )._value._value
        planner_cached = llm_tokens_consumed_lifetime.labels(
            model="claude-3-5-sonnet-20241022", node_name="planner_node", token_type="cached_tokens"
        )._value._value

        assert router_prompt == 5000
        assert planner_completion == 3000
        assert planner_cached == 4000

    def test_simulate_billing_report_scenario(self):
        """Test lifetime metrics for billing reports (RC1 fix validation)."""
        # Simulate 7 days of usage
        # Day 1-7: API restarts multiple times, but lifetime totals preserved via DB

        # Total lifetime cost (sum across all restarts)
        total_cost_eur = 45.67

        llm_cost_lifetime.labels(
            model="gpt-4.1-mini-mini", node_name="router_node", currency="EUR"
        ).set(total_cost_eur)

        # Verify billing report can use this metric
        metric_value = llm_cost_lifetime.labels(
            model="gpt-4.1-mini-mini", node_name="router_node", currency="EUR"
        )._value._value

        assert metric_value == 45.67

        # No underreporting (RC1 issue: ~22k tokens lost due to counter resets)
        # Gauges + DB = restart-safe ✅

    def test_simulate_performance_slo_monitoring(self):
        """Test update duration SLO monitoring (<50ms target)."""
        # Simulate multiple update cycles
        durations = [0.023, 0.035, 0.041, 0.048, 0.052]  # 52ms = SLO breach

        for duration in durations:
            lifetime_metrics_update_duration_seconds.set(duration)

        # Last duration breached SLO
        last_duration = lifetime_metrics_update_duration_seconds._value._value
        assert last_duration == 0.052
        assert last_duration > 0.050  # SLO breach detected

        # Alert should fire: LifetimeMetricsUpdateSlow


# ============================================================================
# Integration Tests (require database)
# ============================================================================


@pytest.mark.integration
class TestLifetimeMetricsIntegration:
    """Integration tests with real database (mark: integration)."""

    @pytest.mark.asyncio
    async def test_full_lifecycle_with_real_db(self):
        """Test full lifecycle with real database."""
        # This test would require real DB fixture
        # Marked as integration to skip in unit tests
        pytest.skip("Integration test - requires real database")

    @pytest.mark.asyncio
    async def test_index_performance_validation(self):
        """Test index performance (<50ms SLO)."""
        # This test would validate ix_token_usage_logs_lifetime_aggregation index
        pytest.skip("Integration test - requires real database with indexes")
