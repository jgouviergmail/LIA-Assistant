"""Peer capability receipts and explicit recipient-authored skill policy.

Revision ID: a94e30f821b6
Revises: 754351d42c74
"""

from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision: str = "a94e30f821b6"
down_revision: str | None = "754351d42c74"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "skills",
        sa.Column("peer_authored", sa.Boolean(), server_default=sa.false(), nullable=False),
    )
    op.drop_constraint("ck_skills_provenance", "skills", type_="check")
    op.create_check_constraint(
        "ck_skills_provenance",
        "skills",
        "provenance IN ('system','authored','url','plugin','library','peer') AND (provenance = 'system') = is_system",
    )
    op.create_table(
        "peer_capability_transfers",
        sa.Column("id", sa.Uuid(), nullable=False, primary_key=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("sender_id", sa.Uuid(), sa.ForeignKey("users.id", ondelete="SET NULL")),
        sa.Column(
            "recipient_id",
            sa.Uuid(),
            sa.ForeignKey("users.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "connection_id",
            sa.Uuid(),
            sa.ForeignKey("peer_connections.id", ondelete="SET NULL"),
        ),
        sa.Column("source_id", sa.Uuid(), nullable=False),
        sa.Column("idempotency_key", sa.Uuid(), nullable=False),
        sa.Column("kind", sa.String(20), nullable=False),
        sa.Column("name", sa.String(100), nullable=False),
        sa.Column("digest", sa.String(64), nullable=False),
        sa.Column("snapshot", postgresql.JSONB()),
        sa.Column("status", sa.String(20), server_default="preparing", nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("transferred_at", sa.DateTime(timezone=True)),
        sa.Column("lease_owner", sa.Uuid()),
        sa.Column("lease_expires_at", sa.DateTime(timezone=True)),
        sa.Column("fence", sa.Integer(), server_default="0", nullable=False),
        sa.Column("error_code", sa.String(64)),
        sa.Column("notification_sent", sa.Boolean(), server_default=sa.false(), nullable=False),
        sa.UniqueConstraint(
            "sender_id", "idempotency_key", name="uq_peer_capability_transfer_request"
        ),
        sa.CheckConstraint(
            "kind IN ('skill','mcp','plugin')", name="ck_peer_capability_transfer_kind"
        ),
        sa.CheckConstraint(
            "status IN ('preparing','installing','installed','partial','failed','cancelled')",
            name="ck_peer_capability_transfer_status",
        ),
        sa.CheckConstraint(
            "sender_id IS NULL OR sender_id <> recipient_id",
            name="ck_peer_capability_transfer_distinct_users",
        ),
    )
    for column in ("sender_id", "recipient_id"):
        op.create_index(
            f"ix_peer_capability_transfers_{column}",
            "peer_capability_transfers",
            [column],
        )
    op.create_table(
        "peer_capability_components",
        sa.Column("id", sa.Uuid(), nullable=False, primary_key=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column(
            "transfer_id",
            sa.Uuid(),
            sa.ForeignKey("peer_capability_transfers.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("kind", sa.String(20), nullable=False),
        sa.Column("key", sa.String(180), nullable=False),
        sa.Column("resource_id", sa.Uuid()),
        sa.Column("fingerprint", sa.String(64), nullable=False),
        sa.Column("installed", sa.Boolean(), server_default=sa.false(), nullable=False),
        sa.Column("error_code", sa.String(64)),
        sa.UniqueConstraint(
            "transfer_id", "kind", "key", name="uq_peer_capability_component_identity"
        ),
        sa.UniqueConstraint("kind", "resource_id", name="uq_peer_capability_component_resource"),
        sa.CheckConstraint(
            "kind IN ('skill','mcp','plugin')", name="ck_peer_capability_component_kind"
        ),
    )
    op.create_index(
        "ix_peer_capability_components_transfer_id",
        "peer_capability_components",
        ["transfer_id"],
    )


def downgrade() -> None:
    op.drop_table("peer_capability_components")
    op.drop_table("peer_capability_transfers")
    op.execute("UPDATE skills SET provenance = 'authored' WHERE provenance = 'peer'")
    op.drop_constraint("ck_skills_provenance", "skills", type_="check")
    op.create_check_constraint(
        "ck_skills_provenance",
        "skills",
        "provenance IN ('system','authored','url','plugin','library') AND (provenance = 'system') = is_system",
    )
    op.drop_column("skills", "peer_authored")
