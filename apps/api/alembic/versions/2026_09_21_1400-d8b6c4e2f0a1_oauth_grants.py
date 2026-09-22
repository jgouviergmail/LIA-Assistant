"""Store one OAuth grant per provider account and link logical connectors.

Revision ID: d8b6c4e2f0a1
Revises: a4c8e1f7b3d5
Create Date: 2026-09-21 14:00:00.000000

Existing connector credentials remain valid and unlinked. They move to a grant
only after a successful, explicitly selected bulk authorization.
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "d8b6c4e2f0a1"
down_revision: str | None = "a4c8e1f7b3d5"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "oauth_grants",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, nullable=False),
        sa.Column("user_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("provider", sa.String(length=20), nullable=False),
        sa.Column("client_id", sa.String(length=255), nullable=False),
        sa.Column("subject", sa.String(length=255), nullable=False),
        sa.Column("email", sa.String(length=320), nullable=True),
        sa.Column("scopes", postgresql.JSONB(), nullable=False),
        sa.Column("credentials_encrypted", sa.Text(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.UniqueConstraint(
            "user_id", "provider", "client_id", "subject", name="uq_oauth_grants_account"
        ),
    )
    op.add_column(
        "connectors", sa.Column("oauth_grant_id", postgresql.UUID(as_uuid=True), nullable=True)
    )
    op.create_foreign_key(
        "fk_connectors_oauth_grant_id",
        "connectors",
        "oauth_grants",
        ["oauth_grant_id"],
        ["id"],
        ondelete="SET NULL",
    )
    op.create_index("ix_connectors_oauth_grant_id", "connectors", ["oauth_grant_id"])


def downgrade() -> None:
    op.drop_index("ix_connectors_oauth_grant_id", table_name="connectors")
    op.drop_constraint("fk_connectors_oauth_grant_id", "connectors", type_="foreignkey")
    op.drop_column("connectors", "oauth_grant_id")
    op.drop_table("oauth_grants")
