"""Add Psyche Engine tables and personality trait columns.

Creates:
- psyche_states: 1:1 dynamic psychological state per user
- psyche_history: Evolution snapshots for tracking

Alters:
- personalities: Add Big Five traits + PAD override columns
- users: Add psyche preferences (enabled, display, sensitivity, stability)

Seeds Big Five + PAD override values for all 14 personalities.

Revision ID: psyche_engine_001
Revises: account_deletion_001
Create Date: 2026-04-01
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers
revision: str = "psyche_engine_001"
down_revision: str | None = "account_deletion_001"
branch_labels = None
depends_on = None


# Big Five trait profiles for each personality
# Format: (code, O, C, E, A, N, pad_p_override, pad_a_override, pad_d_override)
# None = auto-compute from Big Five via Mehrabian mapping
PERSONALITY_TRAITS = [
    ("cynic",        0.80, 0.60, 0.55, 0.25, 0.40, None,  None,  None),
    ("normal",       0.50, 0.70, 0.50, 0.60, 0.30, None,  None,  None),
    ("depressed",    0.65, 0.30, 0.15, 0.40, 0.85, -0.35, -0.40, -0.45),
    ("enthusiastic", 0.70, 0.55, 0.95, 0.80, 0.15, None,  +0.35, None),
    ("friend",       0.55, 0.45, 0.75, 0.90, 0.20, None,  None,  None),
    ("philosopher",  0.95, 0.70, 0.30, 0.55, 0.35, None,  -0.25, None),
    ("influencer",   0.60, 0.35, 0.90, 0.35, 0.30, None,  None,  None),
    ("professor",    0.75, 0.90, 0.55, 0.80, 0.20, None,  None,  None),
    ("rasta",        0.80, 0.20, 0.60, 0.85, 0.05, None,  None,  None),
    ("teenager",     0.40, 0.10, 0.35, 0.20, 0.65, -0.20, +0.15, +0.30),
    ("jarvis",       0.60, 0.95, 0.40, 0.50, 0.10, None,  -0.20, +0.55),
    ("haipai",       0.65, 0.75, 0.85, 0.45, 0.35, None,  None,  None),
    ("trump",        0.20, 0.30, 0.95, 0.05, 0.50, +0.10, +0.55, +0.75),
    ("antagonist",   0.90, 0.80, 0.50, 0.10, 0.30, None,  None,  None),
]


def upgrade() -> None:
    """Create psyche tables and add trait columns."""

    # =========================================================================
    # 1. ALTER TABLE personalities — add Big Five + PAD override columns
    # =========================================================================
    for col_name in [
        "trait_openness", "trait_conscientiousness", "trait_extraversion",
        "trait_agreeableness", "trait_neuroticism",
        "pad_pleasure_override", "pad_arousal_override", "pad_dominance_override",
    ]:
        op.add_column(
            "personalities",
            sa.Column(col_name, sa.Float(), nullable=True),
        )

    # =========================================================================
    # 2. Seed Big Five + PAD override values for all 14 personalities
    # =========================================================================
    personalities_table = sa.table(
        "personalities",
        sa.column("code", sa.String),
        sa.column("trait_openness", sa.Float),
        sa.column("trait_conscientiousness", sa.Float),
        sa.column("trait_extraversion", sa.Float),
        sa.column("trait_agreeableness", sa.Float),
        sa.column("trait_neuroticism", sa.Float),
        sa.column("pad_pleasure_override", sa.Float),
        sa.column("pad_arousal_override", sa.Float),
        sa.column("pad_dominance_override", sa.Float),
    )

    for (code, o, c, e, a, n, pp, pa, pd) in PERSONALITY_TRAITS:
        op.execute(
            personalities_table.update()
            .where(personalities_table.c.code == code)
            .values(
                trait_openness=o,
                trait_conscientiousness=c,
                trait_extraversion=e,
                trait_agreeableness=a,
                trait_neuroticism=n,
                pad_pleasure_override=pp,
                pad_arousal_override=pa,
                pad_dominance_override=pd,
            )
        )

    # =========================================================================
    # 3. ALTER TABLE users — add psyche preference columns
    # =========================================================================
    op.add_column(
        "users",
        sa.Column("psyche_enabled", sa.Boolean(), nullable=False, server_default="false"),
    )
    op.add_column(
        "users",
        sa.Column("psyche_display_mood", sa.Boolean(), nullable=False, server_default="true"),
    )
    op.add_column(
        "users",
        sa.Column("psyche_sensitivity", sa.Integer(), nullable=False, server_default="70"),
    )
    op.add_column(
        "users",
        sa.Column("psyche_stability", sa.Integer(), nullable=False, server_default="60"),
    )

    # =========================================================================
    # 4. CREATE TABLE psyche_states
    # =========================================================================
    op.create_table(
        "psyche_states",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, nullable=False),
        sa.Column(
            "user_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("users.id", ondelete="CASCADE"),
            nullable=False,
            unique=True,
        ),
        # Big Five traits
        sa.Column("trait_openness", sa.Float(), nullable=False, server_default="0.5"),
        sa.Column("trait_conscientiousness", sa.Float(), nullable=False, server_default="0.5"),
        sa.Column("trait_extraversion", sa.Float(), nullable=False, server_default="0.5"),
        sa.Column("trait_agreeableness", sa.Float(), nullable=False, server_default="0.5"),
        sa.Column("trait_neuroticism", sa.Float(), nullable=False, server_default="0.5"),
        # Mood (PAD)
        sa.Column("mood_pleasure", sa.Float(), nullable=False, server_default="0"),
        sa.Column("mood_arousal", sa.Float(), nullable=False, server_default="0"),
        sa.Column("mood_dominance", sa.Float(), nullable=False, server_default="0"),
        sa.Column("mood_quadrant_since", sa.DateTime(timezone=True), nullable=True),
        # Emotions + Self-Efficacy (JSONB)
        sa.Column("active_emotions", postgresql.JSONB(), nullable=True),
        sa.Column("self_efficacy", postgresql.JSONB(), nullable=True),
        # Relationship
        sa.Column("relationship_stage", sa.String(20), nullable=False, server_default="ORIENTATION"),
        sa.Column("relationship_depth", sa.Float(), nullable=False, server_default="0"),
        sa.Column("relationship_warmth_active", sa.Float(), nullable=False, server_default="0.5"),
        sa.Column("relationship_trust", sa.Float(), nullable=False, server_default="0.3"),
        sa.Column("relationship_interaction_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("relationship_total_duration_minutes", sa.Float(), nullable=False, server_default="0"),
        sa.Column("relationship_last_interaction", sa.DateTime(timezone=True), nullable=True),
        # Drives
        sa.Column("drive_curiosity", sa.Float(), nullable=False, server_default="0.5"),
        sa.Column("drive_engagement", sa.Float(), nullable=False, server_default="0.5"),
        # Metadata
        sa.Column("last_appraisal", postgresql.JSONB(), nullable=True),
        sa.Column("narrative_identity", sa.Text(), nullable=True),
        sa.Column("psyche_version", sa.Integer(), nullable=False, server_default="1"),
        # Timestamps
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
    )

    # NOTE: user_id unique constraint already created by unique=True in create_table above

    # =========================================================================
    # 5. CREATE TABLE psyche_history
    # =========================================================================
    op.create_table(
        "psyche_history",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, nullable=False),
        sa.Column(
            "user_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("users.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("snapshot_type", sa.String(30), nullable=False),
        sa.Column("mood_pleasure", sa.Float(), nullable=False, server_default="0"),
        sa.Column("mood_arousal", sa.Float(), nullable=False, server_default="0"),
        sa.Column("mood_dominance", sa.Float(), nullable=False, server_default="0"),
        sa.Column("dominant_emotion", sa.String(30), nullable=True),
        sa.Column("relationship_stage", sa.String(20), nullable=False, server_default="ORIENTATION"),
        sa.Column("trait_snapshot", postgresql.JSONB(), nullable=True),
        # Timestamps
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
    )

    op.create_index(
        "ix_psyche_history_user_created",
        "psyche_history",
        ["user_id", "created_at"],
    )


def downgrade() -> None:
    """Drop psyche tables and remove trait columns."""

    # Drop tables (reverse order)
    op.drop_index("ix_psyche_history_user_created", table_name="psyche_history")
    op.drop_table("psyche_history")

    # unique constraint dropped automatically with table
    op.drop_table("psyche_states")

    # Remove user columns
    for col_name in ["psyche_enabled", "psyche_display_mood", "psyche_sensitivity", "psyche_stability"]:
        op.drop_column("users", col_name)

    # Remove personality columns
    for col_name in [
        "trait_openness", "trait_conscientiousness", "trait_extraversion",
        "trait_agreeableness", "trait_neuroticism",
        "pad_pleasure_override", "pad_arousal_override", "pad_dominance_override",
    ]:
        op.drop_column("personalities", col_name)
