"""Add user_totp + mfa_backup_codes (security program D1, Lot 2 — TOTP).

The TOTP secret is Fernet-encrypted (reversible by design — verification
needs it); backup codes are stored as SHA-256 hashes only (revealed once).
Both purged explicitly at account deletion (soft-delete means the users FK
CASCADE never fires — user_data_map classification USER_PURGED/EXCLUDED).

Revision ID: f7b2d8e14a59
Revises: e5a1c7d93b48
Create Date: 2026-07-23 04:00:00
"""

import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import UUID

from alembic import op

# revision identifiers, used by Alembic.
revision = "f7b2d8e14a59"
down_revision = "e5a1c7d93b48"
branch_labels = None
depends_on = None


def upgrade() -> None:
    """Create the user_totp and mfa_backup_codes tables."""
    op.create_table(
        "user_totp",
        sa.Column("id", UUID(as_uuid=True), primary_key=True, nullable=False),
        sa.Column(
            "user_id",
            UUID(as_uuid=True),
            sa.ForeignKey("users.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "secret_encrypted",
            sa.Text(),
            nullable=False,
            comment="Fernet-encrypted base32 TOTP secret (reversible by design).",
        ),
        sa.Column(
            "confirmed_at",
            sa.DateTime(timezone=True),
            nullable=True,
            comment="Set when the user proves possession with a first valid code.",
        ),
        sa.Column(
            "last_used_step",
            sa.BigInteger(),
            nullable=True,
            comment="Last accepted TOTP timestep (anti-replay within the validity window).",
        ),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("user_id", name="uq_user_totp_user_id"),
    )

    op.create_table(
        "mfa_backup_codes",
        sa.Column("id", UUID(as_uuid=True), primary_key=True, nullable=False),
        sa.Column(
            "user_id",
            UUID(as_uuid=True),
            sa.ForeignKey("users.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "code_hash",
            sa.String(64),
            nullable=False,
            comment="SHA-256 hex digest of the raw backup code (never the raw code).",
        ),
        sa.Column(
            "used_at",
            sa.DateTime(timezone=True),
            nullable=True,
            comment="Set on consumption — a backup code is strictly single-use.",
        ),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("code_hash", name="uq_mfa_backup_codes_code_hash"),
    )
    op.create_index("ix_mfa_backup_codes_user", "mfa_backup_codes", ["user_id"])


def downgrade() -> None:
    """Drop the TOTP tables."""
    op.drop_index("ix_mfa_backup_codes_user", table_name="mfa_backup_codes")
    op.drop_table("mfa_backup_codes")
    op.drop_table("user_totp")
