"""Self-converging grants for the product read views (ADR-178).

View grants die with the views (DROP VIEW) and were applied manually after
migrations — measured twice in prod: the read-only role existed while every
panel answered "permission denied". This migration makes deployments
converge on their own: IF the role exists, re-grant SELECT on the seven
product views (plus schema USAGE). On a virgin database (replay-check, fresh
installs) the role does not exist yet and this is a clean no-op — the
`create_grafana_reader` script keeps owning role creation and password.

Revision ID: e2f3a4b5c6d7
Revises: d1e2f3a4b5c6
Create Date: 2026-07-29 08:00:00.000000
"""

from collections.abc import Sequence

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "e2f3a4b5c6d7"
down_revision: str | None = "d1e2f3a4b5c6"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_ROLE = "grafana_product_reader"
_VIEWS = (
    "product_value_daily",
    "product_depth_daily",
    "product_activation_cohorts_weekly",
    "product_signup_cohorts_weekly",
    "product_routines_snapshot",
    "product_time_to_first_value",
    "product_quality_daily",
)


def upgrade() -> None:
    """Re-grant SELECT on the product views when the role exists (idempotent)."""
    views_sql = ", ".join(_VIEWS)
    op.execute(
        f"""
        DO $$
        BEGIN
            IF EXISTS (SELECT FROM pg_roles WHERE rolname = '{_ROLE}') THEN
                GRANT USAGE ON SCHEMA public TO {_ROLE};
                GRANT SELECT ON {views_sql} TO {_ROLE};
            END IF;
        END
        $$;
        """
    )


def downgrade() -> None:
    """Revoke the view grants when the role exists (views may outlive them)."""
    views_sql = ", ".join(_VIEWS)
    op.execute(
        f"""
        DO $$
        BEGIN
            IF EXISTS (SELECT FROM pg_roles WHERE rolname = '{_ROLE}') THEN
                REVOKE SELECT ON {views_sql} FROM {_ROLE};
            END IF;
        END
        $$;
        """
    )
