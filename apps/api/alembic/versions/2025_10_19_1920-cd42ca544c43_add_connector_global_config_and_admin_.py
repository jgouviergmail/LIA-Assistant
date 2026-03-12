"""add_connector_global_config_and_admin_audit_log

Revision ID: cd42ca544c43
Revises: 090adf8517f4
Create Date: 2025-10-19 19:20:06.313969

"""
from collections.abc import Sequence
from typing import Union

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision: str = 'cd42ca544c43'
down_revision: str | None = '090adf8517f4'
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Add connector_global_config and admin_audit_log tables."""

    # Create connector_global_config table
    op.create_table(
        'connector_global_config',
        sa.Column('id', sa.UUID(), server_default=sa.text('gen_random_uuid()'), nullable=False),
        sa.Column('connector_type', sa.String(length=50), nullable=False),
        sa.Column('is_enabled', sa.Boolean(), server_default=sa.text('true'), nullable=False),
        sa.Column('disabled_reason', sa.Text(), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('connector_type', name='uq_connector_global_config_connector_type')
    )

    # Create index on connector_type for fast lookup
    op.create_index(
        'ix_connector_global_config_connector_type',
        'connector_global_config',
        ['connector_type']
    )

    # Create admin_audit_log table
    op.create_table(
        'admin_audit_log',
        sa.Column('id', sa.UUID(), server_default=sa.text('gen_random_uuid()'), nullable=False),
        sa.Column('admin_user_id', sa.UUID(), nullable=False),
        sa.Column('action', sa.String(length=100), nullable=False),
        sa.Column('resource_type', sa.String(length=50), nullable=False),
        sa.Column('resource_id', sa.UUID(), nullable=True),
        sa.Column('details', sa.JSON(), nullable=True),
        sa.Column('ip_address', sa.String(length=45), nullable=True),
        sa.Column('user_agent', sa.Text(), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.PrimaryKeyConstraint('id'),
        sa.ForeignKeyConstraint(['admin_user_id'], ['users.id'], ondelete='CASCADE')
    )

    # Create indexes for admin_audit_log
    op.create_index(
        'ix_admin_audit_log_admin_user_id',
        'admin_audit_log',
        ['admin_user_id']
    )

    op.create_index(
        'ix_admin_audit_log_action',
        'admin_audit_log',
        ['action']
    )

    op.create_index(
        'ix_admin_audit_log_resource_type',
        'admin_audit_log',
        ['resource_type']
    )

    op.create_index(
        'ix_admin_audit_log_created_at',
        'admin_audit_log',
        ['created_at']
    )


def downgrade() -> None:
    """Remove connector_global_config and admin_audit_log tables."""

    # Drop admin_audit_log
    op.drop_index('ix_admin_audit_log_created_at', table_name='admin_audit_log')
    op.drop_index('ix_admin_audit_log_resource_type', table_name='admin_audit_log')
    op.drop_index('ix_admin_audit_log_action', table_name='admin_audit_log')
    op.drop_index('ix_admin_audit_log_admin_user_id', table_name='admin_audit_log')
    op.drop_table('admin_audit_log')

    # Drop connector_global_config
    op.drop_index('ix_connector_global_config_connector_type', table_name='connector_global_config')
    op.drop_table('connector_global_config')
