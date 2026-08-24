"""Capability provenance and provider deprecation date on llm_models (ADR-244).

``capability_provenance`` distinguishes a measured capability from a column
default: 89 of 114 active rows carried the defaults, which is why
``get_effective_context_window`` returned 8 192 for ``gpt-5.2``.
``deprecation_date`` carries the provider retirement date so a retired model
stops being offered.

Revision ID: a0b1c2d3e4f5
Revises: 9b0c1d2e3f4a
Create Date: 2026-08-24 09:00:00.000000
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "a0b1c2d3e4f5"
down_revision: str | None = "9b0c1d2e3f4a"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_ENUM_NAME = "llm_capability_provenance_enum"
_VALUES = ("declared", "imported", "verified")


def upgrade() -> None:
    """Add the provenance enum column and the deprecation date."""
    provenance = sa.Enum(*_VALUES, name=_ENUM_NAME)
    provenance.create(op.get_bind(), checkfirst=True)
    op.add_column(
        "llm_models",
        sa.Column(
            "capability_provenance",
            provenance,
            nullable=False,
            server_default="declared",
            comment="Authority that filled the capability fields (declared/imported/verified)",
        ),
    )
    op.add_column(
        "llm_models",
        sa.Column(
            "deprecation_date",
            sa.Date(),
            nullable=True,
            comment="Provider retirement date from the vendored registry snapshot",
        ),
    )


def downgrade() -> None:
    """Drop both columns and the enum type."""
    op.drop_column("llm_models", "deprecation_date")
    op.drop_column("llm_models", "capability_provenance")
    sa.Enum(name=_ENUM_NAME).drop(op.get_bind(), checkfirst=True)
