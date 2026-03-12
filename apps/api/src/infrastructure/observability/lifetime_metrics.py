"""
Lifetime Metrics Updater - DB-Backed Prometheus Gauges

Phase 1.2 - Solution for RC1 (Prometheus Counter Resets)

Problem:
    - Prometheus in-memory counters reset on API restart
    - Grafana increase() queries miss pre-restart data
    - Result: ~22k tokens underreported (20% discrepancy)
    - offset-based queries fail when Prometheus lacks historical data

Solution:
    - Hybrid metrics approach:
      * Counters: Real-time increments (traditional Prometheus)
      * Gauges: Lifetime totals from database (restart-safe)
      * Period gauges: Last 24h/7d from database (no Prometheus history needed)
    - Background task syncs DB → Gauges every 30-60s
    - Grafana can query either metric depending on use case

Architecture:

    Token Usage Event → DB Persistence (authoritative)
                     ↓
                  Counter++ (real-time, volatile)
                     ↓
    Background Task (30s interval)
        ↓ Query DB (lifetime + period aggregations)
        ↓ Aggregate by model/node
        ↓ Update Gauges (lifetime + period, persistent)
                     ↓
              Prometheus Scrape
                     ↓
             Grafana Dashboards

Performance:
    - Query interval: 30s (configurable)
    - Query time: <50ms with indexes (from <500ms without)
    - Memory overhead: ~1KB per model/node combination
    - Cache: In-memory dict to skip unchanged values

Best Practices:
    - Gauges for lifetime totals (billing, reports)
    - Period gauges for "today"/"this week" (no Prometheus history dependency)
    - Counters for real-time monitoring (alerting)

References:
    - RC1 Root Cause Analysis
    - ADR-015: Token Tracking Architecture V2
    - Prometheus Best Practices: https://prometheus.io/docs/practices/instrumentation/
"""

import asyncio
from datetime import UTC, datetime, timedelta

import structlog
from prometheus_client import Gauge
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.config import settings
from src.core.field_names import FIELD_NODE_NAME
from src.domains.auth.models import User
from src.domains.chat.models import TokenUsageLog
from src.domains.conversations.models import Conversation, ConversationMessage
from src.infrastructure.database import get_db_context

logger = structlog.get_logger(__name__)

# ============================================================================
# Prometheus Gauges (Lifetime Totals - Restart-Safe)
# ============================================================================

# Token consumption gauges (lifetime totals from database)
llm_tokens_consumed_lifetime = Gauge(
    "llm_tokens_consumed_lifetime",
    "Lifetime LLM token consumption from database (restart-safe)",
    ["model", FIELD_NODE_NAME, "token_type"],
)

# Cost gauges (lifetime totals from database)
llm_cost_lifetime = Gauge(
    "llm_cost_lifetime",
    "Lifetime LLM cost from database (restart-safe)",
    ["model", FIELD_NODE_NAME, "currency"],
)

# ============================================================================
# Prometheus Gauges (Period Totals - DB-Backed, No Prometheus History Needed)
# ============================================================================

# Token consumption gauges (last 24h from database)
llm_tokens_consumed_last_24h = Gauge(
    "llm_tokens_consumed_last_24h",
    "LLM token consumption in last 24 hours from database",
    ["token_type"],
)

# Cost gauges (last 24h from database)
llm_cost_last_24h = Gauge(
    "llm_cost_last_24h",
    "LLM cost in last 24 hours from database",
)

# Token consumption gauges (last 7d from database)
llm_tokens_consumed_last_7d = Gauge(
    "llm_tokens_consumed_last_7d",
    "LLM token consumption in last 7 days from database",
    ["token_type"],
)

# Cost gauges (last 7d from database)
llm_cost_last_7d = Gauge(
    "llm_cost_last_7d",
    "LLM cost in last 7 days from database",
)

# Cost by model (last 24h) for piecharts
llm_cost_by_model_last_24h = Gauge(
    "llm_cost_by_model_last_24h",
    "LLM cost by model in last 24 hours from database",
    ["model"],
)

# Cost by node (last 24h) for piecharts
llm_cost_by_node_last_24h = Gauge(
    "llm_cost_by_node_last_24h",
    "LLM cost by node in last 24 hours from database",
    [FIELD_NODE_NAME],
)

# ============================================================================
# Prometheus Gauges (Activity Period Totals - DB-Backed)
# ============================================================================

# Conversations created in last 24h
conversations_created_last_24h = Gauge(
    "conversations_created_last_24h",
    "Conversations created in last 24 hours from database",
)

# Messages archived in last 24h
messages_archived_last_24h = Gauge(
    "messages_archived_last_24h",
    "Messages archived in last 24 hours from database",
)

# User registrations in last 24h
users_registered_last_24h = Gauge(
    "users_registered_last_24h",
    "User registrations in last 24 hours from database",
)

# Metrics about the updater itself (observability)
lifetime_metrics_update_duration_seconds = Gauge(
    "lifetime_metrics_update_duration_seconds",
    "Duration of lifetime metrics update operation",
)

lifetime_metrics_last_update_timestamp = Gauge(
    "lifetime_metrics_last_update_timestamp",
    "Unix timestamp of last successful lifetime metrics update",
)

lifetime_metrics_error_total = Gauge(
    "lifetime_metrics_error_total",
    "Total number of lifetime metrics update errors since start",
)

# ============================================================================
# In-Memory Cache (Avoid Redundant Gauge Updates)
# ============================================================================

# Cache format: {(model, node): (input_tokens, output_tokens, cached_tokens, cost_eur)}
_lifetime_cache: dict[tuple[str, str], tuple[int, int, int, float]] = {}
_last_update: datetime | None = None
_error_count: int = 0


# ============================================================================
# Main Update Function
# ============================================================================


async def update_lifetime_metrics() -> None:
    """
    Background task: Sync lifetime metrics from database to Prometheus gauges.

    Runs continuously with configurable interval (default: 30s).
    Optimized for performance with caching and incremental updates.

    Optimizations:
        1. In-memory cache: Skip gauge updates if values unchanged
        2. Indexed queries: <50ms aggregation with proper indexes
        3. Batch processing: GROUP BY reduces row scans
        4. Error isolation: Failure doesn't break application

    Metrics Updated:
        - llm_tokens_consumed_lifetime: Total tokens by model/node/type
        - llm_cost_lifetime: Total cost by model/node/currency

    Performance SLOs:
        - Query time: <50ms (with indexes)
        - Update interval: 30s (configurable)
        - Memory overhead: <1KB per model/node combo
        - Error rate: <0.1% (log but continue)

    Usage:
        # In main.py lifespan
        @asynccontextmanager
        async def lifespan(app: FastAPI):
            task = asyncio.create_task(update_lifetime_metrics())
            yield
            task.cancel()
    """
    global _lifetime_cache, _last_update, _error_count

    update_interval = getattr(settings, "lifetime_metrics_update_interval", 30)  # seconds

    logger.info(
        "lifetime_metrics_updater_started",
        update_interval=update_interval,
        message=f"DB-backed gauges will sync every {update_interval}s",
    )

    while True:
        try:
            start_time = datetime.now(UTC)

            async with get_db_context() as db:
                # Execute optimized aggregation queries
                # Uses index: ix_token_usage_logs_lifetime_aggregation
                updated_count = await _sync_metrics_from_db(db)

                # Sync period-based metrics (24h, 7d) from DB
                await _sync_period_metrics_from_db(db)

                # Update metadata gauges
                duration = (datetime.now(UTC) - start_time).total_seconds()
                lifetime_metrics_update_duration_seconds.set(duration)
                lifetime_metrics_last_update_timestamp.set(datetime.now(UTC).timestamp())

                _last_update = start_time

                logger.debug(
                    "lifetime_metrics_updated",
                    updated_count=updated_count,
                    duration_seconds=round(duration, 3),
                    cache_size=len(_lifetime_cache),
                    interval=update_interval,
                )

            # Sleep until next update
            await asyncio.sleep(update_interval)

        except asyncio.CancelledError:
            logger.info(
                "lifetime_metrics_updater_cancelled",
                total_updates=len(_lifetime_cache),
                error_count=_error_count,
            )
            break

        except Exception as e:
            _error_count += 1
            lifetime_metrics_error_total.set(_error_count)

            logger.error(
                "lifetime_metrics_update_failed",
                error=str(e),
                error_type=type(e).__name__,
                error_count=_error_count,
                exc_info=True,
            )

            # Continue despite error (don't break application)
            # Use exponential backoff on repeated errors
            backoff = min(update_interval * (2 ** min(_error_count - 1, 5)), 300)
            await asyncio.sleep(backoff)


async def _sync_metrics_from_db(db: AsyncSession) -> int:
    """
    Execute database query and update Prometheus gauges.

    Query optimized with indexes for <50ms execution time.

    Args:
        db: Async database session

    Returns:
        Number of gauge series updated

    Query Pattern:
        SELECT model_name, node_name,
               SUM(input_tokens), SUM(output_tokens), SUM(cached_tokens),
               SUM(cost_eur)
        FROM token_usage_logs
        GROUP BY model_name, node_name
    """
    global _lifetime_cache

    # Build aggregation query
    # Uses index: ix_token_usage_logs_lifetime_aggregation (model_name, node_name, created_at)
    stmt = select(
        TokenUsageLog.model_name,
        TokenUsageLog.node_name,
        func.sum(TokenUsageLog.prompt_tokens).label("total_input"),
        func.sum(TokenUsageLog.completion_tokens).label("total_output"),
        func.sum(TokenUsageLog.cached_tokens).label("total_cached"),
        func.sum(TokenUsageLog.cost_eur).label("total_cost_eur"),
    ).group_by(TokenUsageLog.model_name, TokenUsageLog.node_name)

    # Execute query
    result = await db.execute(stmt)
    rows = result.all()

    updated_count = 0

    for row in rows:
        cache_key = (row.model_name, row.node_name)

        # Build current values tuple
        current_values = (
            row.total_input or 0,
            row.total_output or 0,
            row.total_cached or 0,
            float(row.total_cost_eur or 0),
        )

        # Check cache: skip if unchanged (optimization)
        if cache_key in _lifetime_cache and _lifetime_cache[cache_key] == current_values:
            continue  # No change, skip gauge update

        # Update token gauges
        llm_tokens_consumed_lifetime.labels(
            model=row.model_name, **{FIELD_NODE_NAME: row.node_name}, token_type="prompt_tokens"
        ).set(row.total_input or 0)

        llm_tokens_consumed_lifetime.labels(
            model=row.model_name, **{FIELD_NODE_NAME: row.node_name}, token_type="completion_tokens"
        ).set(row.total_output or 0)

        llm_tokens_consumed_lifetime.labels(
            model=row.model_name, **{FIELD_NODE_NAME: row.node_name}, token_type="cached_tokens"
        ).set(row.total_cached or 0)

        # Update cost gauge (EUR by default, configurable)
        currency = settings.default_currency.upper()
        llm_cost_lifetime.labels(
            model=row.model_name, **{FIELD_NODE_NAME: row.node_name}, currency=currency
        ).set(float(row.total_cost_eur or 0))

        # Update cache
        _lifetime_cache[cache_key] = current_values
        updated_count += 1

    return updated_count


async def _sync_period_metrics_from_db(db: AsyncSession) -> None:
    """
    Sync period-based (24h, 7d) metrics from database to Prometheus gauges.

    Unlike lifetime metrics, these query with a date filter:
        WHERE created_at > now() - interval 'X'

    This is immune to Prometheus restart/history gaps — the DB is the
    single source of truth for period aggregations.
    """
    now = datetime.now(UTC)

    for period_hours, cost_gauge, tokens_gauge, cost_by_model_gauge, cost_by_node_gauge in [
        (
            24,
            llm_cost_last_24h,
            llm_tokens_consumed_last_24h,
            llm_cost_by_model_last_24h,
            llm_cost_by_node_last_24h,
        ),
        (168, llm_cost_last_7d, llm_tokens_consumed_last_7d, None, None),
    ]:
        cutoff = now - timedelta(hours=period_hours)

        # Aggregate tokens by type
        token_stmt = select(
            func.sum(TokenUsageLog.prompt_tokens).label("total_input"),
            func.sum(TokenUsageLog.completion_tokens).label("total_output"),
            func.sum(TokenUsageLog.cached_tokens).label("total_cached"),
            func.sum(TokenUsageLog.cost_eur).label("total_cost_eur"),
        ).where(TokenUsageLog.created_at >= cutoff)

        result = await db.execute(token_stmt)
        row = result.one()

        tokens_gauge.labels(token_type="prompt_tokens").set(row.total_input or 0)
        tokens_gauge.labels(token_type="completion_tokens").set(row.total_output or 0)
        tokens_gauge.labels(token_type="cached_tokens").set(row.total_cached or 0)
        cost_gauge.set(float(row.total_cost_eur or 0))

        # By-model and by-node breakdowns (only for 24h)
        if cost_by_model_gauge is not None and cost_by_node_gauge is not None:
            # Reset all previously set labels to avoid stale series
            cost_by_model_gauge._metrics.clear()
            cost_by_node_gauge._metrics.clear()

            # Cost by model
            model_stmt = (
                select(
                    TokenUsageLog.model_name,
                    func.sum(TokenUsageLog.cost_eur).label("cost"),
                )
                .where(TokenUsageLog.created_at >= cutoff)
                .group_by(TokenUsageLog.model_name)
            )
            for mrow in (await db.execute(model_stmt)).all():
                cost_val = float(mrow.cost or 0)
                if cost_val > 0:
                    cost_by_model_gauge.labels(model=mrow.model_name).set(cost_val)

            # Cost by node
            node_stmt = (
                select(
                    TokenUsageLog.node_name,
                    func.sum(TokenUsageLog.cost_eur).label("cost"),
                )
                .where(TokenUsageLog.created_at >= cutoff)
                .group_by(TokenUsageLog.node_name)
            )
            for nrow in (await db.execute(node_stmt)).all():
                cost_val = float(nrow.cost or 0)
                if cost_val > 0:
                    cost_by_node_gauge.labels(**{FIELD_NODE_NAME: nrow.node_name}).set(cost_val)

    # Activity period metrics (conversations, messages, users)
    cutoff_24h = now - timedelta(hours=24)

    # Conversations created in last 24h
    conv_count = await db.scalar(
        select(func.count()).select_from(Conversation).where(Conversation.created_at >= cutoff_24h)
    )
    conversations_created_last_24h.set(conv_count or 0)

    # Messages archived in last 24h
    msg_count = await db.scalar(
        select(func.count())
        .select_from(ConversationMessage)
        .where(ConversationMessage.created_at >= cutoff_24h)
    )
    messages_archived_last_24h.set(msg_count or 0)

    # Users registered in last 24h
    user_count = await db.scalar(
        select(func.count()).select_from(User).where(User.created_at >= cutoff_24h)
    )
    users_registered_last_24h.set(user_count or 0)


# ============================================================================
# Manual Refresh (for testing/debugging)
# ============================================================================


async def refresh_lifetime_metrics_now() -> dict[str, int | float]:
    """
    Manually trigger immediate refresh of lifetime metrics.

    Useful for:
        - Testing during development
        - Debugging metric discrepancies
        - Post-deployment validation

    Example:
        >>> from src.infrastructure.observability.lifetime_metrics import refresh_lifetime_metrics_now
        >>> await refresh_lifetime_metrics_now()
        {'updated_count': 42, 'duration_seconds': 0.045}
    """
    start_time = datetime.now(UTC)

    async with get_db_context() as db:
        updated_count = await _sync_metrics_from_db(db)
        await _sync_period_metrics_from_db(db)

    duration = (datetime.now(UTC) - start_time).total_seconds()

    logger.info(
        "lifetime_metrics_manual_refresh",
        updated_count=updated_count,
        duration_seconds=round(duration, 3),
    )

    return {"updated_count": updated_count, "duration_seconds": duration}


# ============================================================================
# Exports
# ============================================================================

__all__ = [
    "update_lifetime_metrics",
    "refresh_lifetime_metrics_now",
    # Gauges - Lifetime totals
    "llm_tokens_consumed_lifetime",
    "llm_cost_lifetime",
    # Gauges - Period totals (DB-backed, no Prometheus history needed)
    "llm_tokens_consumed_last_24h",
    "llm_cost_last_24h",
    "llm_tokens_consumed_last_7d",
    "llm_cost_last_7d",
    "llm_cost_by_model_last_24h",
    "llm_cost_by_node_last_24h",
    # Gauges - Activity period totals
    "conversations_created_last_24h",
    "messages_archived_last_24h",
    "users_registered_last_24h",
]
