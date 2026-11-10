"""Each deciding JEV usage stores its thresholds in system_settings (ADR-374).

Revision ID: 77a44a46135f
Revises: 2bd1b9347e2c
Create Date: 2026-11-08 03:00:00.000000

The upgrade writes nothing: a missing ``JEV_<USAGE>_THRESHOLDS`` row reads as the declared
defaults (``jev_gates.py``), and the administrator writes one only by moving a gate. The
downgrade deletes those rows: the former code does not declare these ``SystemSettingKey``
members, and ``Enum(native_enum=False)`` would raise ``LookupError`` on every unfiltered
read of ``system_settings``. The thresholds the former code used are its constants.
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "77a44a46135f"
down_revision: str | None = "2bd1b9347e2c"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_USAGES = (
    "MEETING_TEMPLATE",
    "RADIO_VERIFICATION",
    "CONSULTATION_PATH",
    "CONSULTATION_BOUNDED",
    "HITL_EXCLUSION",
    "HITL_REJECTION",
    "MEMORY_REFERENCE_PRESENCE",
    "PARAMETER_KIND",
    "EMAIL_CLASSIFICATION",
    "EVENT_CLASSIFICATION",
)

_FORGET_THE_THRESHOLDS = sa.text("DELETE FROM system_settings WHERE key IN :keys").bindparams(
    sa.bindparam("keys", value=[f"JEV_{usage}_THRESHOLDS" for usage in _USAGES], expanding=True)
)


def upgrade() -> None:
    """Nothing to write: an absent row reads as the declared defaults."""


def downgrade() -> None:
    """Remove the rows the former code cannot read."""
    op.execute(_FORGET_THE_THRESHOLDS)
