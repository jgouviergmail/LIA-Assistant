"""Add webauthn_credentials (security program D1, Lot 1 — passkeys).

Stores public passkey material only (credential id, COSE public key,
signature counter): private keys never leave the user's authenticator.
Purged explicitly at account deletion (soft-delete means the users FK
CASCADE never fires — user_data_map classification USER_PURGED/EXCLUDED).

Revision ID: e5a1c7d93b48
Revises: c9f1a2b8d374
Create Date: 2026-07-23 03:00:00
"""

import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB, UUID

from alembic import op

# revision identifiers, used by Alembic.
revision = "e5a1c7d93b48"
down_revision = "c9f1a2b8d374"
branch_labels = None
depends_on = None


def upgrade() -> None:
    """Create the webauthn_credentials table."""
    op.create_table(
        "webauthn_credentials",
        sa.Column("id", UUID(as_uuid=True), primary_key=True, nullable=False),
        sa.Column(
            "user_id",
            UUID(as_uuid=True),
            sa.ForeignKey("users.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "credential_id",
            sa.Text(),
            nullable=False,
            comment="Base64url-encoded WebAuthn credential ID (public identifier).",
        ),
        sa.Column(
            "public_key",
            sa.Text(),
            nullable=False,
            comment=(
                "Base64url-encoded COSE public key (verification material, not secret-usable)."
            ),
        ),
        sa.Column(
            "sign_count",
            sa.BigInteger(),
            nullable=False,
            server_default="0",
            comment="Last verified signature counter (clone detection; 0 for synced passkeys).",
        ),
        sa.Column(
            "transports",
            JSONB,
            nullable=True,
            comment="Authenticator transports reported at registration (internal, hybrid, usb…).",
        ),
        sa.Column(
            "aaguid",
            sa.String(36),
            nullable=True,
            comment="Authenticator AAGUID (model identifier, may be zeroed by the platform).",
        ),
        sa.Column(
            "device_type",
            sa.String(32),
            nullable=True,
            comment="py_webauthn credential_device_type: single_device | multi_device.",
        ),
        sa.Column(
            "backed_up",
            sa.Boolean(),
            nullable=False,
            server_default=sa.false(),
            comment="Whether the credential is synced/backed up (multi-device passkey).",
        ),
        sa.Column(
            "label",
            sa.String(64),
            nullable=True,
            comment="Optional user-supplied label (e.g. 'iPhone', 'PC bureau').",
        ),
        sa.Column(
            "last_used_at",
            sa.DateTime(timezone=True),
            nullable=True,
            comment="Updated on each successful authentication.",
        ),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("credential_id", name="uq_webauthn_credentials_credential_id"),
    )
    op.create_index("ix_webauthn_credentials_user", "webauthn_credentials", ["user_id"])


def downgrade() -> None:
    """Drop the webauthn_credentials table."""
    op.drop_index("ix_webauthn_credentials_user", table_name="webauthn_credentials")
    op.drop_table("webauthn_credentials")
