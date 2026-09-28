"""A generated file can be kept past its deadline (ADR-319).

Revision ID: 6c871f348887
Revises: fe0475369c8e
Create Date: 2026-09-25 16:00:00.000000

``attachments.expires_at`` becomes nullable: NULL means the person kept the file
from the gallery, and the cleanup — which selects ``expires_at <= now()`` —
never reaches it, by the SQL semantics of NULL rather than by a filter someone
must remember to write. A CHECK keeps the invariant an upload relies on: an
upload always has a deadline (keeping is a gallery act, and the gallery lists
what LIA produced).

No row changes on the way up. The way down gives every kept file the deadline
it would get if it were released now (the TTL counted from the downgrade), then
restores NOT NULL: the previous code cannot read a NULL deadline.
"""

from __future__ import annotations

import os
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "6c871f348887"
down_revision: str | None = "fe0475369c8e"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_COMMENT = (
    "When the cleanup removes the file; NULL = kept by the person "
    "(generated files only, ADR-319)."
)

#: The TTL the previous code applies (``ATTACHMENTS_TTL_HOURS`` default), read
#: from the environment when it is set so a downgrade honours the deployment.
_DOWNGRADE_TTL_HOURS_DEFAULT = 24


def upgrade() -> None:
    """Allow a NULL deadline (kept), for generated files only."""
    op.alter_column(
        "attachments",
        "expires_at",
        existing_type=sa.DateTime(timezone=True),
        nullable=True,
        comment=_COMMENT,
    )
    op.create_check_constraint(
        "ck_attachments_upload_expires",
        "attachments",
        "expires_at IS NOT NULL OR origin <> 'upload'",
    )


def downgrade() -> None:
    """Give every kept file a deadline again, then restore NOT NULL."""
    ttl_hours = int(os.environ.get("ATTACHMENTS_TTL_HOURS") or _DOWNGRADE_TTL_HOURS_DEFAULT)
    op.drop_constraint("ck_attachments_upload_expires", "attachments", type_="check")
    op.execute(
        sa.text(
            "UPDATE attachments SET expires_at = now() + make_interval(hours => :hours) "
            "WHERE expires_at IS NULL"
        ).bindparams(hours=ttl_hours)
    )
    op.alter_column(
        "attachments",
        "expires_at",
        existing_type=sa.DateTime(timezone=True),
        nullable=False,
        comment=None,
        existing_comment=_COMMENT,
    )
