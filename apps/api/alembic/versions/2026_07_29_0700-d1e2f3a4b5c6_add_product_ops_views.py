"""Three more product read views (ADR-178 — dashboard 26 v2).

Replaces stale text placeholders with real data: routines health snapshot
(AUT-01/02/13 from scheduled_actions state columns), signup→first-value
percentiles per weekly cohort (ACT-03), and daily outcome quality counts
(first-pass proxy = produced without correction). Aggregate columns only —
no PII crosses the read-only role boundary; grants come from
``scripts.data.create_grafana_reader`` (re-run after migrating).

Revision ID: d1e2f3a4b5c6
Revises: c0d1e2f3a4b5
Create Date: 2026-07-29 07:00:00.000000
"""

from collections.abc import Sequence

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "d1e2f3a4b5c6"
down_revision: str | None = "c0d1e2f3a4b5"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_VIEWS: dict[str, str] = {
    "product_routines_snapshot": """
        CREATE VIEW product_routines_snapshot AS
        SELECT count(*) AS total,
               count(*) FILTER (WHERE is_enabled) AS enabled,
               count(*) FILTER (WHERE execution_count > 0) AS executed_at_least_once,
               count(*) FILTER (WHERE is_enabled AND consecutive_failures > 0)
                   AS enabled_failing,
               count(*) FILTER (WHERE NOT is_enabled AND consecutive_failures > 0)
                   AS disabled_with_failures,
               max(consecutive_failures) AS max_consecutive_failures,
               count(DISTINCT user_id) AS users_with_routines
        FROM scheduled_actions
    """,
    "product_time_to_first_value": """
        CREATE VIEW product_time_to_first_value AS
        WITH first_value AS (
            SELECT user_id, min(validated_at) AS first_validated_at
            FROM product_outcomes
            WHERE state = 'validated'
            GROUP BY user_id
        )
        SELECT date_trunc('week', u.created_at) AS cohort_week,
               count(*) AS users,
               percentile_cont(0.5) WITHIN GROUP (
                   ORDER BY EXTRACT(EPOCH FROM (fv.first_validated_at - u.created_at))
               ) AS p50_seconds,
               percentile_cont(0.95) WITHIN GROUP (
                   ORDER BY EXTRACT(EPOCH FROM (fv.first_validated_at - u.created_at))
               ) AS p95_seconds
        FROM first_value fv
        JOIN users u ON u.id = fv.user_id
        GROUP BY 1
    """,
    "product_quality_daily": """
        CREATE VIEW product_quality_daily AS
        SELECT date_trunc('day', produced_at) AS day,
               count(*) AS produced,
               count(*) FILTER (WHERE state = 'validated') AS validated,
               count(*) FILTER (WHERE corrected) AS corrected,
               count(*) FILTER (WHERE state = 'rejected') AS rejected
        FROM product_outcomes
        GROUP BY 1
    """,
}


def upgrade() -> None:
    """Create the three ops read views."""
    for ddl in _VIEWS.values():
        op.execute(ddl)


def downgrade() -> None:
    """Drop the three ops read views."""
    for view in reversed(list(_VIEWS)):
        op.execute(f"DROP VIEW IF EXISTS {view}")
