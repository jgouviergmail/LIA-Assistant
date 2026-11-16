"""ntfy subscriptions: a topic on a server the person's apps subscribe to (ADR-391).

Revision ID: b7b4b7c9dd28
Revises: d7f104891aef
Create Date: 2026-11-16 01:00:00.000000

One row per topic an account receives LIA's notifications on. The topic is a password and the
token a credential: both encrypted. An instance subscription names no server (the operator's,
read at send time); a custom one names a public https server.
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = "b7b4b7c9dd28"
down_revision: str | None = "d7f104891aef"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Create the subscriptions table."""
    op.create_table(
        "ntfy_subscriptions",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, nullable=False),
        sa.Column(
            "user_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("users.id", ondelete="CASCADE"),
            nullable=False,
            comment="The account the notifications are for.",
        ),
        sa.Column(
            "server_kind",
            sa.String(10),
            nullable=False,
            comment="instance (the operator's server) | custom (a public server the person chose).",
        ),
        sa.Column(
            "server_url",
            sa.Text(),
            nullable=True,
            comment="The custom server's https address; NULL for the instance server.",
        ),
        sa.Column(
            "topic_encrypted",
            sa.Text(),
            nullable=False,
            comment="The topic, encrypted: it is a password.",
        ),
        sa.Column(
            "token_encrypted",
            sa.Text(),
            nullable=True,
            comment="The person's access token on a custom server, encrypted.",
        ),
        sa.Column(
            "content",
            sa.String(10),
            nullable=False,
            server_default="minimal",
            comment="minimal (a notice that LIA has something) | full (the words themselves).",
        ),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default="true"),
        sa.Column(
            "last_sent_at",
            sa.DateTime(timezone=True),
            nullable=True,
            comment="Last publication the server accepted.",
        ),
        sa.Column(
            "last_error_code",
            sa.String(32),
            nullable=True,
            comment="Outcome of the last refused publication (NtfyOutcome).",
        ),
        sa.Column("last_error_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint("server_kind IN ('instance', 'custom')", name="ck_ntfy_server_kind"),
        sa.CheckConstraint(
            "(server_kind = 'instance') = (server_url IS NULL)", name="ck_ntfy_server_url"
        ),
        sa.CheckConstraint(
            "server_kind = 'custom' OR token_encrypted IS NULL", name="ck_ntfy_instance_token"
        ),
        sa.CheckConstraint("content IN ('minimal', 'full')", name="ck_ntfy_content"),
    )
    op.create_index("ix_ntfy_subscriptions_user_id", "ntfy_subscriptions", ["user_id"])


def downgrade() -> None:
    """Drop the subscriptions table."""
    op.drop_index("ix_ntfy_subscriptions_user_id", table_name="ntfy_subscriptions")
    op.drop_table("ntfy_subscriptions")
