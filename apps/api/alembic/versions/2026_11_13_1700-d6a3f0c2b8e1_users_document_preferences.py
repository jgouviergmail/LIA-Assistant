"""How a person wants their generated documents made.

Revision ID: d6a3f0c2b8e1
Revises: 41dd8c9c2117

Two choices on the account, read by the document tool at every generation:
whether LIA illustrates a document (``auto``, ``on_request``, ``never``) and
whether it animates a deck (``presented``, ``always``, ``never``). The server
defaults are the owner's defaults (2026-11-13), so every existing account gets
them in the same statement that adds the column.
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "d6a3f0c2b8e1"
down_revision: str | Sequence[str] | None = "41dd8c9c2117"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

# The owner's defaults when this revision was written (core/document_preferences.py).
_ILLUSTRATIONS_DEFAULT = "auto"
_ANIMATIONS_DEFAULT = "presented"


def upgrade() -> None:
    op.add_column(
        "users",
        sa.Column(
            "document_illustrations",
            sa.String(length=20),
            nullable=False,
            server_default=_ILLUSTRATIONS_DEFAULT,
            comment="Illustrations in generated documents: auto, on_request, never.",
        ),
    )
    op.add_column(
        "users",
        sa.Column(
            "document_animations",
            sa.String(length=20),
            nullable=False,
            server_default=_ANIMATIONS_DEFAULT,
            comment="Animations in generated decks: presented, always, never.",
        ),
    )


def downgrade() -> None:
    op.drop_column("users", "document_animations")
    op.drop_column("users", "document_illustrations")
