"""The relationship debrief: one LLM-written synthesis per person, per local day.

One row per ``(user, identity)`` — the CURRENT debrief, never a history: the
artefact's only value is being the latest one, and every source it was written
from is already owned by the account.

The row is a CLAIM as well as a payload. ``state`` says whether a build is in
flight, settled, failed or found nothing to say; ``claim_owner`` and
``held_until`` are its lease. ``held_until`` carries two meanings that read the
same way — *not available before this instant*: the lease a crashed builder
leaves behind, and the cooldown a failure leaves behind. One column, one
predicate, no second state machine.

``generated_for`` is the user's LOCAL date: "once a day" is a promise about the
reader's day, and a UTC boundary would rebuild at 2 a.m. for half of Europe.

``users.relation_debrief_enabled`` lands in the same migration because the
feature and its off switch ship together — a capability whose only control
arrives one release later is one nobody can decline.

Revision ID: 625745c6e5ee
Revises: f0a1b2c3d4e5
Create Date: 2026-09-07 00:00:00.000000
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "625745c6e5ee"
down_revision: str | None = "f0a1b2c3d4e5"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Create ``relation_debriefs`` and the per-user off switch."""
    op.create_table(
        "relation_debriefs",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column(
            "user_id",
            postgresql.UUID(as_uuid=True),
            nullable=False,
            comment="Owner of the debrief. Dies with the account.",
        ),
        sa.Column(
            "name_key",
            sa.String(length=255),
            nullable=False,
            comment="Canonical folded identity (IdentityResolver), merges applied.",
        ),
        sa.Column(
            "display_name",
            sa.String(length=255),
            nullable=False,
            comment="Spelling the debrief was written about.",
        ),
        sa.Column(
            "generated_for",
            sa.Date(),
            nullable=False,
            comment="The user's LOCAL date this debrief belongs to (once a day).",
        ),
        sa.Column(
            "generated_at",
            sa.DateTime(timezone=True),
            nullable=True,
            comment="UTC instant the BODY was produced; preserved by a no-change rebuild.",
        ),
        sa.Column(
            "language",
            sa.String(length=10),
            nullable=False,
            comment="Backend-canonical language it was written in (zh-CN, never zh).",
        ),
        sa.Column(
            "scope_digest",
            sa.String(length=64),
            nullable=False,
            comment="Digest of the 360° scope it was written under; a change rebuilds.",
        ),
        sa.Column(
            "evidence_digest",
            sa.String(length=64),
            nullable=True,
            comment="Digest of the evidence fed to the model; compared only at rebuild.",
        ),
        sa.Column(
            "sections_used",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
            comment="Sections the debrief actually read — the honesty contract.",
        ),
        sa.Column(
            "unavailable",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
            comment="Sections asked for that could not be read.",
        ),
        sa.Column(
            "body",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=True,
            comment="Versioned structured payload; NULL until a build settles.",
        ),
        sa.Column(
            "state",
            sa.Enum(
                "building",
                "ready",
                "failed",
                "empty",
                name="debriefstate",
                native_enum=False,
                length=16,
                create_constraint=True,
            ),
            nullable=False,
            comment="building | ready | failed | empty",
        ),
        sa.Column(
            "claim_owner",
            postgresql.UUID(as_uuid=True),
            nullable=True,
            comment="Token of the builder holding this row; a settle quotes it or is refused.",
        ),
        sa.Column(
            "held_until",
            sa.DateTime(timezone=True),
            nullable=True,
            comment="Not available before this instant: a building lease, or a failed cooldown.",
        ),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("user_id", "name_key", name="uq_relation_debriefs_user_name"),
    )
    op.create_index(
        "ix_relation_debriefs_user_state",
        "relation_debriefs",
        ["user_id", "state"],
        unique=False,
    )
    op.add_column(
        "users",
        sa.Column(
            "relation_debrief_enabled",
            sa.Boolean(),
            nullable=False,
            server_default="true",
            comment="User preference for the daily relationship debrief. True = enabled.",
        ),
    )


def downgrade() -> None:
    """Drop the table and the preference."""
    op.drop_column("users", "relation_debrief_enabled")
    op.drop_index("ix_relation_debriefs_user_state", table_name="relation_debriefs")
    op.drop_table("relation_debriefs")
