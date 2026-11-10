"""Add an independent blind display-search projection; old rows remain candidates.

Revision ID: c83a51f09d62
Revises: b74d02e6a193
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "c83a51f09d62"
down_revision = "b74d02e6a193"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "sms_search_terms",
        sa.Column("display_hashes", postgresql.ARRAY(sa.LargeBinary(32)), nullable=True),
    )
    op.add_column("sms_search_terms", sa.Column("display_version", sa.Integer(), nullable=True))
    op.add_column(
        "sms_search_terms",
        sa.Column(
            "display_complete", sa.Boolean(), nullable=False, server_default=sa.text("false")
        ),
    )
    op.create_index(
        "ix_sms_display_terms_gin", "sms_search_terms", ["display_hashes"], postgresql_using="gin"
    )


def downgrade() -> None:
    op.execute(
        "UPDATE sms_messages AS message SET logical_bytes = message.logical_bytes - 32 * COALESCE(cardinality(projection.display_hashes), 0) FROM sms_search_terms AS projection WHERE projection.message_id = message.id AND projection.user_id = message.user_id"
    )
    op.drop_index("ix_sms_display_terms_gin", table_name="sms_search_terms")
    op.drop_column("sms_search_terms", "display_complete")
    op.drop_column("sms_search_terms", "display_version")
    op.drop_column("sms_search_terms", "display_hashes")
