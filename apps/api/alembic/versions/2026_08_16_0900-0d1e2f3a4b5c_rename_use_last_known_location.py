"""Rename users.weather_use_last_known_location to use_last_known_location.

The last-known location opt-in was shipped weather-scoped (ADR-073): the flag
gated only the proactive weather cascade. The 2026-08-16 generalization makes
the persisted last-known location a first-class source for EVERY feature
(chat tool resolution, scheduled actions, briefing, interests), so the name
must stop claiming a weather-only scope — a name describing behavior the code
does not have is the same defect as a lying docstring.

Pure rename: no data movement, no type change, no default change. The
frontend and backend deploy together (monorepo release), so no compatibility
alias is kept.

Revision ID: 0d1e2f3a4b5c
Revises: d9e0f1a2b3c4
Create Date: 2026-08-16 09:00:00.000000
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "0d1e2f3a4b5c"
down_revision: str | None = "d9e0f1a2b3c4"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_TABLE = "users"
_OLD = "weather_use_last_known_location"
_NEW = "use_last_known_location"

# The comment travels with the rename: the replay gate compares the rebuilt
# schema against the model, and a column claiming a weather-only scope under
# a generalized name would be structural drift.
_OLD_COMMENT = (
    "Opt-in for using the persisted browser geolocation in proactive "
    "weather notifications when the user is away from home. False = "
    "home-only (default)."
)
_NEW_COMMENT = (
    "Opt-in for using the persisted browser geolocation across all "
    "features (chat tools, scheduled actions, proactive jobs) when the "
    "live position is unavailable. False = home-only (default)."
)


def upgrade() -> None:
    """Rename the opt-in column to its generalized name."""
    op.alter_column(
        _TABLE,
        _OLD,
        new_column_name=_NEW,
        existing_type=sa.Boolean(),
        existing_nullable=False,
        existing_server_default=sa.text("false"),
        comment=_NEW_COMMENT,
        existing_comment=_OLD_COMMENT,
    )


def downgrade() -> None:
    """Restore the weather-scoped column name."""
    op.alter_column(
        _TABLE,
        _NEW,
        new_column_name=_OLD,
        existing_type=sa.Boolean(),
        existing_nullable=False,
        existing_server_default=sa.text("false"),
        comment=_OLD_COMMENT,
        existing_comment=_NEW_COMMENT,
    )
