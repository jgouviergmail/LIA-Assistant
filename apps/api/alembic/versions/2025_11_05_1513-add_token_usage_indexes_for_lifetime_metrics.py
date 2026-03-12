"""Add indexes for token_usage_logs to optimize lifetime metrics queries

Revision ID: token_usage_indexes_lifetime
Revises: (previous migration)
Create Date: 2025-11-05 15:13:00.000000

Context:
    Phase 1.2 - DB-Backed Gauges for Prometheus Restart-Safe Metrics

    Problem (RC1 - Prometheus Counter Resets):
        - In-memory Prometheus counters reset on API restart
        - Grafana increase() queries miss pre-restart data
        - Result: ~22k tokens underreported (20% discrepancy)

    Solution:
        - DB-backed Prometheus gauges that persist across restarts
        - Background task queries database every 30-60s to update gauges
        - Indexes optimize these recurring aggregation queries

    Performance Impact:
        - Without indexes: ~500ms+ for aggregation query on 1M+ rows
        - With indexes: <50ms for same query
        - Background task runs every 30s, so performance is critical

Indexes Created:
    1. ix_token_usage_logs_lifetime_aggregation (composite B-tree)
       - Columns: (model_name, node_name, created_at)
       - Purpose: Optimize GROUP BY model/node aggregations
       - Query pattern: SELECT SUM(tokens) GROUP BY model_name, node_name

    2. ix_token_usage_logs_recent (partial B-tree with DESC)
       - Columns: (model_name, node_name, created_at DESC)
       - Condition: created_at >= CURRENT_DATE - INTERVAL '30 days'
       - Purpose: Optimize queries on recent data (smaller index)
       - Query pattern: Recent aggregations (last 30 days)

    3. ix_token_usage_logs_model_node (covering B-tree)
       - Columns: (model_name, node_name) INCLUDE (input_tokens, output_tokens, cached_tokens, cost_eur)
       - Purpose: Index-only scans for full table aggregations
       - Query pattern: SELECT SUM(tokens), SUM(cost) for all time

Query Examples Optimized:

    # Total tokens by model/node (lifetime)
    SELECT model_name, node_name,
           SUM(input_tokens) as total_input,
           SUM(output_tokens) as total_output,
           SUM(cached_tokens) as total_cached,
           SUM(cost_eur) as total_cost
    FROM token_usage_logs
    GROUP BY model_name, node_name;

    # Recent tokens (last 30 days)
    SELECT model_name, node_name,
           SUM(input_tokens + output_tokens + cached_tokens) as total
    FROM token_usage_logs
    WHERE created_at >= CURRENT_DATE - INTERVAL '30 days'
    GROUP BY model_name, node_name;

Index Maintenance:
    - Indexes auto-maintained by PostgreSQL
    - Partial index (recent) is smaller → faster updates
    - Covering index enables index-only scans → no table access
    - ANALYZE run after creation to update statistics

References:
    - RC1 Root Cause Analysis (TOKEN_ALIGNMENT_ANALYSIS.md)
    - ADR-015: Token Tracking Architecture V2
    - Phase 1.2: DB-Backed Gauges Implementation Plan
"""

from alembic import op

# Revision identifiers
revision = "token_usage_indexes_lifetime"
down_revision = "seed_openai_pricing"  # Points to seed_openai_pricing migration
branch_labels = None
depends_on = None


def upgrade():
    """
    Add optimized indexes for lifetime metrics aggregation queries.

    Performance targets:
        - Aggregation query: <50ms (currently 500ms+ without indexes)
        - Background update interval: 30s
        - Index size: <10% of table size
    """

    # ========================================================================
    # Index 1: Composite B-tree for GROUP BY aggregations
    # ========================================================================
    # Optimizes: GROUP BY model_name, node_name with created_at ordering
    # Use case: Lifetime aggregations with time-based partitioning
    op.create_index(
        "ix_token_usage_logs_lifetime_aggregation",
        "token_usage_logs",
        ["model_name", "node_name", "created_at"],
        unique=False,
        postgresql_using="btree",
        postgresql_ops={"created_at": "DESC"},  # Recent data accessed more frequently
    )

    # ========================================================================
    # Index 2: Simple index for date-based filtering
    # ========================================================================
    # Optimizes: Queries filtered by time range
    # Use case: Dashboard queries (last 24h, last 7d, last 30d)
    # Note: Partial index with CURRENT_DATE removed (not IMMUTABLE)
    op.create_index(
        "ix_token_usage_logs_created_at",
        "token_usage_logs",
        ["created_at"],
        unique=False,
        postgresql_using="btree",
        postgresql_ops={"created_at": "DESC"},
    )

    # ========================================================================
    # Index 3: Covering index for full table aggregations (INCLUDE columns)
    # ========================================================================
    # Optimizes: SUM(tokens), SUM(cost) without table access (index-only scan)
    # Use case: Lifetime total queries (all data, no time filter)
    # Benefit: No table I/O → 2-3x faster for covering queries
    op.execute(
        """
        CREATE INDEX ix_token_usage_logs_model_node_covering
        ON token_usage_logs (model_name, node_name)
        INCLUDE (prompt_tokens, completion_tokens, cached_tokens, cost_eur, created_at)
        """
    )

    # ========================================================================
    # Update PostgreSQL statistics for query planner
    # ========================================================================
    # Ensures planner uses new indexes immediately
    op.execute("ANALYZE token_usage_logs")

    print("✅ Token usage indexes created successfully")
    print("   - Composite index: ix_token_usage_logs_lifetime_aggregation")
    print("   - Created_at index: ix_token_usage_logs_created_at")
    print("   - Covering index: ix_token_usage_logs_model_node_covering")
    print("   - Statistics updated: ANALYZE completed")


def downgrade():
    """
    Remove indexes created in upgrade().

    Note: Safe to rollback - no data loss, only performance impact.
    """

    # Drop covering index (with INCLUDE clause)
    op.execute("DROP INDEX IF EXISTS ix_token_usage_logs_model_node_covering")

    # Drop created_at index
    op.drop_index(
        "ix_token_usage_logs_created_at",
        table_name="token_usage_logs",
        postgresql_using="btree",
    )

    # Drop composite index
    op.drop_index(
        "ix_token_usage_logs_lifetime_aggregation",
        table_name="token_usage_logs",
        postgresql_using="btree",
    )

    # Update statistics after index removal
    op.execute("ANALYZE token_usage_logs")

    print("✅ Token usage indexes removed successfully")
