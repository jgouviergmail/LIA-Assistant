"""The sixteen domain-agent slots leave with the nodes that read them (ADR-371).

Revision ID: b6d21f7e4a90
Revises: 7c3e91a4d2f6
Create Date: 2026-11-06 20:00:00.000000

No graph node reads these slots any more, the plan executor having called the tools directly
for a long time, and the administration screen no longer lists them: a row left behind would be
configuration nobody reads and nobody can reach. ``emails_agent`` stays, the mail tools write with
it. The downgrade writes nothing: the former code reads a slot's default when it has no row.
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "b6d21f7e4a90"
down_revision: str | None = "7c3e91a4d2f6"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_RETIRE_THE_SLOTS = sa.text("""
    DELETE FROM llm_config_overrides
    WHERE llm_type IN (
        'brave_agent', 'calendar_agent', 'contacts_agent', 'drive_agent', 'health_agent',
        'hue_agent', 'perplexity_agent', 'places_agent', 'routes_agent', 'sms_agent',
        'tasks_agent', 'telephony_agent', 'weather_agent', 'web_fetch_agent',
        'web_search_agent', 'wikipedia_agent'
    )
""")


def upgrade() -> None:
    """Remove the rows of the retired slots."""
    op.execute(_RETIRE_THE_SLOTS)


def downgrade() -> None:
    """Write nothing back: the former code falls back on each slot's default."""
