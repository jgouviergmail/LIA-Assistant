"""The person may ask for their image prompts to be enhanced (ADR-315).

Revision ID: 79db1056a28e
Revises: a19e985e4ce5
Create Date: 2026-09-24 20:00:00.000000

``users.image_generation_prompt_enhancement``: the opt-in for rewriting an image
prompt with recognised prompting techniques before the image model is called.
NOT NULL with a server default of ``false``, so every existing account keeps
exactly what it had — nothing is rewritten until the person turns it on.

Downgrade drops the column: the previous code never reads it.
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "79db1056a28e"
down_revision: str | None = "a19e985e4ce5"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Add the opt-in, off for every existing account."""
    op.add_column(
        "users",
        sa.Column(
            "image_generation_prompt_enhancement",
            sa.Boolean(),
            nullable=False,
            server_default="false",
            comment=(
                "User opt-in for rewriting image prompts with recognised prompting "
                "techniques before generation (ADR-315)."
            ),
        ),
    )


def downgrade() -> None:
    """Drop the opt-in."""
    op.drop_column("users", "image_generation_prompt_enhancement")
