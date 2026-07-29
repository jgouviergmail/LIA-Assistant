"""Create/refresh the read-only Grafana product role (ADR-178, Phase 3).

Idempotent by design (decision #4 — a password never lives in a versioned
migration): creates the ``grafana_product_reader`` LOGIN role when absent,
always re-applies the password (rotation-friendly), pins a statement_timeout
on the role (the 'no unbounded SQL from Grafana' acceptance criterion), and
grants SELECT on the product read views ONLY — never on base tables (the
views run with their owner's privileges, so aggregate columns are exposed
without any PII table access).

Usage (from within the API container):
    GRAFANA_PRODUCT_DB_PASSWORD=... python -m scripts.data.create_grafana_reader

Environment:
    GRAFANA_PRODUCT_DB_PASSWORD  (required) — the role password, injected by
    the operator; also given to the Grafana container for the provisioned
    datasource (compose files).
"""

import asyncio
import os
import sys
from pathlib import Path

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent.parent))

import structlog
from sqlalchemy import text

from src.infrastructure.database.session import AsyncSessionLocal

logger = structlog.get_logger(__name__)

ROLE_NAME = "grafana_product_reader"
STATEMENT_TIMEOUT = "10s"
#: The ONLY objects the role may read (product aggregate views, no PII).
PRODUCT_READ_VIEWS = (
    "product_value_daily",
    "product_depth_daily",
    "product_activation_cohorts_weekly",
    "product_signup_cohorts_weekly",
    "product_routines_snapshot",
    "product_time_to_first_value",
    "product_quality_daily",
)


def _quote_literal(value: str) -> str:
    """Escape a string for embedding in DDL (DDL cannot be parameterized)."""
    return value.replace("'", "''")


async def create_grafana_reader(password: str) -> None:
    """Create or refresh the read-only role and its scoped grants.

    Args:
        password: Role password (from GRAFANA_PRODUCT_DB_PASSWORD).

    Raises:
        RuntimeError: If a product read view is missing (migrations not run).
    """
    pwd = _quote_literal(password)
    async with AsyncSessionLocal() as session:
        for view in PRODUCT_READ_VIEWS:
            present = await session.execute(
                text("SELECT 1 FROM pg_views WHERE viewname = :v"), {"v": view}
            )
            if present.fetchone() is None:
                raise RuntimeError(
                    f"View '{view}' missing — run 'task db:migrate' before this script."
                )

        await session.execute(
            text(
                f"""
                DO $$
                BEGIN
                    IF NOT EXISTS (
                        SELECT FROM pg_roles WHERE rolname = '{ROLE_NAME}'
                    ) THEN
                        CREATE ROLE {ROLE_NAME} LOGIN PASSWORD '{pwd}';
                    END IF;
                END
                $$;
                """
            )
        )
        # Always re-applied: password rotation + timeout stay converged.
        await session.execute(
            text(f"ALTER ROLE {ROLE_NAME} WITH LOGIN PASSWORD '{pwd}'")
        )
        await session.execute(
            text(
                f"ALTER ROLE {ROLE_NAME} SET statement_timeout = '{STATEMENT_TIMEOUT}'"
            )
        )
        db_row = await session.execute(text("SELECT current_database()"))
        db_name = db_row.scalar_one()
        await session.execute(
            text(f'GRANT CONNECT ON DATABASE "{db_name}" TO {ROLE_NAME}')
        )
        await session.execute(text(f"GRANT USAGE ON SCHEMA public TO {ROLE_NAME}"))
        for view in PRODUCT_READ_VIEWS:
            await session.execute(text(f"GRANT SELECT ON {view} TO {ROLE_NAME}"))
        await session.commit()

    logger.info(
        "grafana_reader_role_ready",
        role=ROLE_NAME,
        views=list(PRODUCT_READ_VIEWS),
        statement_timeout=STATEMENT_TIMEOUT,
    )
    print(f"OK: role '{ROLE_NAME}' ready (SELECT on {len(PRODUCT_READ_VIEWS)} views only).")


def main() -> None:
    """CLI entry point."""
    password = os.environ.get("GRAFANA_PRODUCT_DB_PASSWORD", "")
    if not password:
        print("ERROR: GRAFANA_PRODUCT_DB_PASSWORD is required.", file=sys.stderr)
        sys.exit(1)
    asyncio.run(create_grafana_reader(password))


if __name__ == "__main__":
    main()
