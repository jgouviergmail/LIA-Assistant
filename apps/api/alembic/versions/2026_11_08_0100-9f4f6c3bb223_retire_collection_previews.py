"""The eight JEV collection previews leave with their switches and slots (ADR-374).

Revision ID: 9f4f6c3bb223
Revises: d2f6b8c4e1a7
Create Date: 2026-11-08 01:00:00.000000

Their only surface, the « first results » panel, was hidden on 2026-10-04 and nothing else read
what they streamed. The code no longer declares their ``SystemSettingKey`` members, so a row left
behind would make every unfiltered read of ``system_settings`` raise ``LookupError``
(``Enum(native_enum=False)`` stores the member NAME); this migration runs before that code
boots. The downgrade writes nothing: the former code reads a missing switch as off, and a
missing slot row as that slot's default.
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "9f4f6c3bb223"
down_revision: str | None = "d2f6b8c4e1a7"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_KINDS = ("EMAIL", "EVENT", "TASK", "FILE", "REMINDER", "TICKET", "MCP", "DOCUMENT")

_RETIRE_THE_SWITCHES = sa.text("DELETE FROM system_settings WHERE key IN :keys").bindparams(
    sa.bindparam("keys", value=[f"JEV_FILTER_{kind}_ENABLED" for kind in _KINDS], expanding=True)
)
_RETIRE_THE_SLOTS = sa.text("DELETE FROM llm_config_overrides WHERE llm_type IN :slots").bindparams(
    sa.bindparam("slots", value=[f"jev_filter_{kind.lower()}" for kind in _KINDS], expanding=True)
)


def upgrade() -> None:
    """Remove the rows of the retired switches and slots."""
    op.execute(_RETIRE_THE_SWITCHES)
    op.execute(_RETIRE_THE_SLOTS)


def downgrade() -> None:
    """Write nothing back: a missing switch reads as off, a missing slot as its default."""
