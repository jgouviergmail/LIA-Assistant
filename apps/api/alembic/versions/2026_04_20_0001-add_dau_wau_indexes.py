"""Add indexes for observability periodic gauges (DAU/WAU + daily conversations).

The `lifetime_metrics` background task (runs every 30s) executes queries that
aggregate conversations by `updated_at` (DAU/WAU) and by `created_at`
(daily-conversation histogram). Without dedicated indexes these queries
degrade to full table scans on the conversations table.

Three new indexes:
- `ix_conversations_updated_at`: supports DAU/WAU `count(distinct user_id)
  WHERE updated_at >= cutoff` in lifetime_metrics.
- `ix_conversations_created_at`: supports daily-conversations-per-user
  `GROUP BY user_id WHERE created_at >= cutoff_24h`. While
  `ix_conversations_user_created` covers many cases, a standalone
  `created_at` index lets the planner range-scan efficiently when no
  user_id predicate is present.
- `ix_connectors_status`: supports the connector_activation_rate Gauge
  `GROUP BY connector_type WHERE status = 'active'`.

Revision ID: obs_indexes_001
Revises: last_known_loc_001
Create Date: 2026-04-20
"""

from collections.abc import Sequence

from alembic import op

revision: str = "obs_indexes_001"
down_revision: str | None = "last_known_loc_001"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Add indexes supporting periodic observability queries."""
    # DAU/WAU — count(distinct user_id) filtered by updated_at range
    op.create_index(
        "ix_conversations_updated_at",
        "conversations",
        ["updated_at"],
        if_not_exists=True,
    )

    # Daily-conversations histogram — group by user_id after created_at range filter
    op.create_index(
        "ix_conversations_created_at",
        "conversations",
        ["created_at"],
        if_not_exists=True,
    )

    # connector_activation_rate — group by connector_type filtered on active status
    op.create_index(
        "ix_connectors_status",
        "connectors",
        ["status"],
        if_not_exists=True,
    )


def downgrade() -> None:
    """Drop the observability indexes."""
    op.drop_index("ix_connectors_status", table_name="connectors", if_exists=True)
    op.drop_index("ix_conversations_created_at", table_name="conversations", if_exists=True)
    op.drop_index("ix_conversations_updated_at", table_name="conversations", if_exists=True)
