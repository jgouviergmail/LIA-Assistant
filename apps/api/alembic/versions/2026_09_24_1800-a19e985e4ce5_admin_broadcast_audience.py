"""A broadcast says who it was addressed to (ADR-312).

Revision ID: a19e985e4ce5
Revises: 402dd18bbf2a
Create Date: 2026-09-24 18:00:00.000000

A targeted broadcast was stored without its recipients: SSE and FCM reached the
chosen accounts at send time, and ``GET /notifications/broadcasts/unread`` then
served it to EVERY account at its next sign-in, since the unread query had
nothing to filter on. ``admin_broadcasts.audience`` (``all`` | ``selected``)
and ``admin_broadcast_recipients`` carry the audience from now on.

The backfill reads what the send route always wrote into the admin audit log
(``action = 'admin_broadcast_sent'``, ``details.is_targeted`` and
``details.target_user_ids``): a targeted broadcast becomes ``selected`` and gets
one recipient row per listed account that STILL EXISTS. A broadcast with no
audit row, or an audit row whose list is null, a scalar or holds a non-UUID,
keeps what it effectively was — ``all`` — and never aborts the upgrade. The
statements are idempotent (a second run changes nothing).

Downgrade drops the table and the column: the previous code reads neither.
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = "a19e985e4ce5"
down_revision: str | None = "402dd18bbf2a"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_AUDIENCE_COMMENT = (
    "Who the broadcast is addressed to: all (every active account at send "
    "time) | selected (the admin_broadcast_recipients rows) — ADR-312."
)

# The audit rows of targeted sends, their list proven to be a JSON array.
_TARGETED_AUDITS = """
    SELECT a.resource_id AS broadcast_id, a.details -> 'target_user_ids' AS targets
    FROM admin_audit_log a
    WHERE a.action = 'admin_broadcast_sent'
      AND a.resource_type = 'broadcast'
      AND a.resource_id IS NOT NULL
      AND jsonb_typeof(a.details -> 'is_targeted') = 'boolean'
      AND (a.details ->> 'is_targeted')::boolean
      AND jsonb_typeof(a.details -> 'target_user_ids') = 'array'
"""

#: Read by the integration test too, so what it proves is what the upgrade runs.
BACKFILL_STATEMENTS: tuple[str, ...] = (
    f"""
    UPDATE admin_broadcasts b
    SET audience = 'selected'
    FROM ({_TARGETED_AUDITS}) t
    WHERE t.broadcast_id = b.id
    """,
    f"""
    INSERT INTO admin_broadcast_recipients (id, created_at, updated_at, broadcast_id, user_id)
    SELECT gen_random_uuid(), b.created_at, b.created_at, b.id, u.id
    FROM ({_TARGETED_AUDITS}) t
    JOIN admin_broadcasts b ON b.id = t.broadcast_id
    CROSS JOIN LATERAL jsonb_array_elements_text(t.targets) AS target(raw_id)
    JOIN users u
      ON target.raw_id ~* '^[0-9a-f]{{8}}-[0-9a-f]{{4}}-[0-9a-f]{{4}}-[0-9a-f]{{4}}-[0-9a-f]{{12}}$'
     AND u.id = target.raw_id::uuid
    ON CONFLICT ON CONSTRAINT uq_admin_broadcast_recipients DO NOTHING
    """,
)


def upgrade() -> None:
    """Add the audience column and the recipients table, then backfill both."""
    op.add_column(
        "admin_broadcasts",
        sa.Column(
            "audience",
            sa.String(length=20),
            nullable=False,
            server_default="all",
            comment=_AUDIENCE_COMMENT,
        ),
    )
    op.create_table(
        "admin_broadcast_recipients",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column(
            "broadcast_id",
            postgresql.UUID(as_uuid=True),
            nullable=False,
            comment="The selected-audience broadcast",
        ),
        sa.Column(
            "user_id",
            postgresql.UUID(as_uuid=True),
            nullable=False,
            comment="An account the broadcast is addressed to",
        ),
        sa.ForeignKeyConstraint(["broadcast_id"], ["admin_broadcasts.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("broadcast_id", "user_id", name="uq_admin_broadcast_recipients"),
    )
    op.create_index(
        "ix_admin_broadcast_recipients_user_id",
        "admin_broadcast_recipients",
        ["user_id"],
        unique=False,
    )
    for statement in BACKFILL_STATEMENTS:
        op.execute(sa.text(statement))


def downgrade() -> None:
    """Drop the recipients table and the column; the previous code reads neither."""
    op.drop_index("ix_admin_broadcast_recipients_user_id", table_name="admin_broadcast_recipients")
    op.drop_table("admin_broadcast_recipients")
    op.drop_column("admin_broadcasts", "audience")
