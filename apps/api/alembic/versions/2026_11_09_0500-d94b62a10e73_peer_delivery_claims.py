"""Fence peer delivery ownership and retain generated text across dispatch retries.

Revision ID: d94b62a10e73
Revises: c83a51f09d62
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "d94b62a10e73"
down_revision = "c83a51f09d62"
branch_labels = None
depends_on = None


def upgrade() -> None:
    """Persist lease ownership and rendition checkpoints before retryable delivery."""
    op.add_column(
        "peer_messages", sa.Column("claim_token", postgresql.UUID(as_uuid=True), nullable=True)
    )
    op.add_column(
        "peer_messages",
        sa.Column("claim_generation", sa.Integer(), nullable=False, server_default="0"),
    )
    op.add_column(
        "peer_messages", sa.Column("lease_expires_at", sa.DateTime(timezone=True), nullable=True)
    )
    op.add_column(
        "peer_messages",
        sa.Column(
            "generation_started", sa.Boolean(), nullable=False, server_default=sa.text("false")
        ),
    )
    op.add_column(
        "peer_messages",
        sa.Column(
            "prepared_text_encrypted",
            sa.Text(),
            nullable=True,
            comment="Encrypted rendition awaiting atomic archival; same retention TTL.",
        ),
    )
    # An old worker's in-flight outcome cannot be inferred at a rolling upgrade.
    # Deployment must drain the old scheduler before upgrading; never re-send it.
    op.execute(
        "UPDATE peer_messages SET status='failed', last_error='generation_outcome_unknown' WHERE status='delivering'"
    )


def downgrade() -> None:
    """Retire checkpoints before restoring the previous delivery schema."""
    # Old workers cannot consume the new checkpoints safely. Close in-flight rows.
    op.execute(
        "UPDATE peer_messages SET status='failed', last_error='delivery_version_retired' WHERE status IN ('pending', 'delivering') AND generation_started"
    )
    for name in (
        "prepared_text_encrypted",
        "generation_started",
        "lease_expires_at",
        "claim_generation",
        "claim_token",
    ):
        op.drop_column("peer_messages", name)
