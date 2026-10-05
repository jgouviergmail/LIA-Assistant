"""Personal speaking-avatar opt-in and connector availability.

Revision ID: a4c7e9f1b3d5
Revises: ef46f93d7745
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "a4c7e9f1b3d5"
down_revision: str | None = "ef46f93d7745"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "users",
        sa.Column(
            "speaking_avatar_enabled", sa.Boolean(), nullable=False, server_default=sa.false(),
            comment="Opt-in for a persistent speaking avatar on the person's Simli key.",
        ),
    )
    # ConnectorType uses VARCHAR (native_enum=False), uppercase enum member names.
    op.execute(sa.text("""
        INSERT INTO connector_global_config (id, connector_type, is_enabled, created_at, updated_at)
        VALUES (gen_random_uuid(), 'SIMLI', true, now(), now())
        ON CONFLICT (connector_type) DO NOTHING
    """))


def downgrade() -> None:
    op.execute(sa.text("DELETE FROM connector_global_config WHERE connector_type = 'SIMLI'"))
    op.drop_column("users", "speaking_avatar_enabled")
