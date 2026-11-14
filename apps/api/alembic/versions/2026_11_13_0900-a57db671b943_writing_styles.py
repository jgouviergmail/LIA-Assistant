"""Learn how the person writes their e-mails, from their sent mail.

Revision ID: a57db671b943
Revises: c4d9e1f7a2b5

A reply LIA drafts reads in the register of the RECEIVED e-mail and signs with no
name: two people answering the same message got the same reply (ADR-383). One row
per account now holds a style profile a model wrote from the person's latest sent
e-mails — how they write, never what they wrote about — encrypted at rest, with how
many e-mails it was learned from and when (a NULL profile: built, nothing learned).
``users.writing_style_enabled`` is the person's switch, ON for every account: no
profile exists until LIA first writes an e-mail for them, so turning it on for the
existing accounts reads nothing today.
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "a57db671b943"
down_revision: str | Sequence[str] | None = "c4d9e1f7a2b5"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Create the profile table and the person's switch."""
    op.create_table(
        "writing_styles",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("user_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column(
            "profile_encrypted",
            sa.Text(),
            nullable=True,
            comment="The style profile, encrypted at rest; NULL = the sent mail taught no style.",
        ),
        sa.Column(
            "mails_read",
            sa.Integer(),
            nullable=False,
            comment="How many sent e-mails the profile was learned from.",
        ),
        sa.Column(
            "built_at",
            sa.DateTime(timezone=True),
            nullable=False,
            comment="When the profile was learned (UTC); it is learned again once too old.",
        ),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("user_id"),
    )
    op.add_column(
        "users",
        sa.Column(
            "writing_style_enabled",
            sa.Boolean(),
            server_default="true",
            nullable=False,
            comment="User preference: drafts follow the style learned from the sent mail.",
        ),
    )


def downgrade() -> None:
    """Drop the switch and the profiles (what was learned is lost)."""
    op.drop_column("users", "writing_style_enabled")
    op.drop_table("writing_styles")
