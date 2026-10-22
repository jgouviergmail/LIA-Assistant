"""Keep the cache reads and Google requests of a ticket's LAST run.

The ticket's total already counted all five figures of the chat meter, while
its last run kept three (input, output, euros): the panel could not show what
that run read from the cache nor how many Google requests it made, though the
total beside it did (owner report 2026-10-21).

The backfill copies what the settle read at the time from the run's own summary
row (``message_token_summary``, the authority ``WorkboardRepository.run_usage``
reads first); where only the per-node rows remain (``token_usage_logs``, the
settle's fallback), the cache reads come from them and the Google count, which
those rows do not carry, stays NULL — unknown, never a zero nobody measured.

Revision ID: 1173db815a53
Revises: 51e5625a4e85
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "1173db815a53"
down_revision: str | None = "51e5625a4e85"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

#: Module-level so the integration test proves these very statements, in this
#: order: the run's own summary row first, then the per-node rows for a run no
#: summary covers. ``token_usage_logs`` holds every call of every account: the
#: aggregate reads only the runs a ticket settled (its ``run_id`` index), never
#: the whole table.
BACKFILL_STATEMENTS: tuple[str, ...] = (
    "UPDATE workboard_tickets AS t "
    "SET last_run_tokens_cache = s.total_cached_tokens, "
    "last_run_google_requests = s.google_api_requests "
    "FROM message_token_summary AS s "
    "WHERE s.run_id = t.last_run_id AND t.last_run_tokens_in IS NOT NULL",
    "UPDATE workboard_tickets AS t "
    "SET last_run_tokens_cache = l.cache "
    "FROM (SELECT run_id, COALESCE(SUM(cached_tokens), 0) AS cache "
    "FROM token_usage_logs "
    "WHERE run_id IN (SELECT last_run_id FROM workboard_tickets "
    "WHERE last_run_tokens_in IS NOT NULL AND last_run_tokens_cache IS NULL) "
    "GROUP BY run_id) AS l "
    "WHERE l.run_id = t.last_run_id AND t.last_run_tokens_in IS NOT NULL "
    "AND t.last_run_tokens_cache IS NULL",
)


def upgrade() -> None:
    op.add_column(
        "workboard_tickets",
        sa.Column(
            "last_run_tokens_cache",
            sa.Integer(),
            nullable=True,
            comment="Cached prompt tokens the last run read.",
        ),
    )
    op.add_column(
        "workboard_tickets",
        sa.Column(
            "last_run_google_requests",
            sa.Integer(),
            nullable=True,
            comment="Google API requests the last run made.",
        ),
    )
    for statement in BACKFILL_STATEMENTS:
        op.execute(sa.text(statement))


def downgrade() -> None:
    op.drop_column("workboard_tickets", "last_run_google_requests")
    op.drop_column("workboard_tickets", "last_run_tokens_cache")
