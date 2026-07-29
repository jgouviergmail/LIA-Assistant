"""Add the product read views for the Grafana datasource (ADR-178, Phase 3).

Plain views (no MATERIALIZED — locking refresh is foreign to the codebase);
they run with their owner's privileges, so granting SELECT on the views to
``grafana_product_reader`` exposes ONLY aggregate columns, never the base
tables (users, product_outcomes). Volumes stay bounded by the 180-day raw
retention purge.

Revision ID: b9c0d1e2f3a4
Revises: a8b9c0d1e2f3
Create Date: 2026-07-29 05:00:00.000000
"""

from collections.abc import Sequence

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "b9c0d1e2f3a4"
down_revision: str | None = "a8b9c0d1e2f3"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_VIEWS: dict[str, str] = {
    "product_value_daily": """
        CREATE VIEW product_value_daily AS
        SELECT date_trunc('day', validated_at) AS day,
               evidence_level,
               result_type,
               domain,
               device_class,
               locale,
               count(*) AS outcomes,
               count(DISTINCT user_id) AS users,
               sum(cost_eur) AS cost_eur
        FROM product_outcomes
        WHERE state = 'validated'
        GROUP BY 1, 2, 3, 4, 5, 6
    """,
    "product_depth_daily": """
        CREATE VIEW product_depth_daily AS
        SELECT day,
               percentile_cont(0.5) WITHIN GROUP (ORDER BY cnt) AS median_results,
               percentile_cont(0.75) WITHIN GROUP (ORDER BY cnt) AS p75_results,
               count(*) AS users
        FROM (
            SELECT date_trunc('day', validated_at) AS day,
                   user_id,
                   count(*) AS cnt
            FROM product_outcomes
            WHERE state = 'validated'
            GROUP BY 1, 2
        ) per_user
        GROUP BY day
    """,
    "product_activation_cohorts_weekly": """
        CREATE VIEW product_activation_cohorts_weekly AS
        SELECT date_trunc('week', u.created_at) AS cohort_week,
               date_trunc('week', o.validated_at) AS active_week,
               count(DISTINCT o.user_id) AS users
        FROM product_outcomes o
        JOIN users u ON u.id = o.user_id
        WHERE o.state = 'validated'
        GROUP BY 1, 2
    """,
    "product_signup_cohorts_weekly": """
        CREATE VIEW product_signup_cohorts_weekly AS
        SELECT date_trunc('week', created_at) AS cohort_week,
               count(*) AS registered
        FROM users
        GROUP BY 1
    """,
}


def upgrade() -> None:
    """Create the four product read views."""
    for ddl in _VIEWS.values():
        op.execute(ddl)


def downgrade() -> None:
    """Drop the product read views."""
    for view in reversed(list(_VIEWS)):
        op.execute(f"DROP VIEW IF EXISTS {view}")
