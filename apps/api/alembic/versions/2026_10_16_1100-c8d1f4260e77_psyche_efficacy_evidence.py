"""Create private Psyche evidence with generation and eviction fences.

Revision ID: c8d1f4260e77
Revises: b62a8d193f04
"""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "c8d1f4260e77"
down_revision: str | None = "b62a8d193f04"
branch_labels: None = None
depends_on: None = None


def upgrade() -> None:
    op.add_column(
        "psyche_states",
        sa.Column(
            "efficacy_generation",
            postgresql.UUID(as_uuid=True),
            nullable=False,
            server_default=sa.text("gen_random_uuid()"),
        ),
    )
    # No historical score is converted into an observation.
    op.add_column("psyche_states", sa.Column("efficacy_profile", postgresql.JSONB(), nullable=True))
    op.add_column(
        "psyche_states", sa.Column("efficacy_evicted_at", sa.DateTime(timezone=True), nullable=True)
    )
    op.add_column(
        "psyche_states",
        sa.Column("efficacy_evicted_message_id", postgresql.UUID(as_uuid=True), nullable=True),
    )
    op.create_table(
        "psyche_efficacy_episodes",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("user_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("state_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("generation", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("run_id", sa.String(128), nullable=False),
        sa.Column("message_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("terminal_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("observations", postgresql.JSONB(), nullable=False),
        sa.Column("config_fingerprint", sa.String(64), nullable=False),
        sa.Column("feedback", sa.String(16), nullable=True),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["state_id"], ["psyche_states.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("user_id", "generation", "run_id", name="uq_efficacy_episode_run"),
        sa.UniqueConstraint(
            "user_id", "generation", "message_id", name="uq_efficacy_episode_message"
        ),
        sa.CheckConstraint(
            "feedback IS NULL OR feedback IN ('helpful', 'unhelpful')",
            name="ck_efficacy_episode_feedback",
        ),
        sa.CheckConstraint(
            "jsonb_typeof(observations) = 'array' AND jsonb_array_length(observations) <= 2",
            name="ck_efficacy_episode_observations",
        ),
    )
    op.create_index(
        "ix_efficacy_episode_owner_time",
        "psyche_efficacy_episodes",
        ["user_id", "generation", "terminal_at", "message_id"],
    )
    # Match application-side defaults: only the migration backfills existing rows.
    op.alter_column("psyche_states", "efficacy_generation", server_default=None)


def downgrade() -> None:
    op.drop_index("ix_efficacy_episode_owner_time", table_name="psyche_efficacy_episodes")
    op.drop_table("psyche_efficacy_episodes")
    for name in (
        "efficacy_evicted_message_id",
        "efficacy_evicted_at",
        "efficacy_profile",
        "efficacy_generation",
    ):
        op.drop_column("psyche_states", name)
