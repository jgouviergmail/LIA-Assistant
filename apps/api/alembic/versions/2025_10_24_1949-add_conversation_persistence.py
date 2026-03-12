"""add_conversation_persistence

Revision ID: conversation_persist_001
Revises: 5421aa3ae914
Create Date: 2025-10-24 19:49:00.000000

Adds conversation persistence infrastructure:
- conversations: User conversation container
- conversation_messages: Message archival for UI
- conversation_audit_log: Immutable audit trail
- Modifies message_token_summary to link to conversations
"""
from collections.abc import Sequence
from typing import Union

import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB

from alembic import op

# revision identifiers, used by Alembic.
revision: str = 'conversation_persist_001'
down_revision: str | None = '5421aa3ae914'
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # Create conversations table
    op.create_table(
        'conversations',
        sa.Column('id', sa.UUID(), nullable=False),
        sa.Column('user_id', sa.UUID(), nullable=False),
        sa.Column('title', sa.String(length=500), nullable=True),
        sa.Column('message_count', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('total_tokens', sa.BigInteger(), nullable=False, server_default='0'),
        sa.Column('deleted_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False, server_default=sa.text('now()')),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False, server_default=sa.text('now()')),
        sa.ForeignKeyConstraint(['user_id'], ['users.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('user_id', name='uq_conversations_user_id')
    )

    # Indexes for conversations
    op.create_index('ix_conversations_user_id', 'conversations', ['user_id'])
    op.create_index('ix_conversations_deleted_at', 'conversations', ['deleted_at'])
    op.create_index('ix_conversations_user_created', 'conversations', ['user_id', 'created_at'])

    # Create conversation_messages table
    op.create_table(
        'conversation_messages',
        sa.Column('id', sa.UUID(), nullable=False),
        sa.Column('conversation_id', sa.UUID(), nullable=False),
        sa.Column('role', sa.String(length=20), nullable=False),
        sa.Column('content', sa.Text(), nullable=False),
        sa.Column('message_metadata', JSONB, nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False, server_default=sa.text('now()')),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False, server_default=sa.text('now()')),
        sa.ForeignKeyConstraint(['conversation_id'], ['conversations.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id')
    )

    # Indexes for conversation_messages
    op.create_index('ix_conversation_messages_conversation_id', 'conversation_messages', ['conversation_id'])
    op.create_index(
        'ix_conversation_messages_conv_created',
        'conversation_messages',
        ['conversation_id', sa.text('created_at DESC')],
        postgresql_using='btree'
    )

    # Create conversation_audit_log table (immutable, no updated_at)
    op.create_table(
        'conversation_audit_log',
        sa.Column('id', sa.UUID(), nullable=False),
        sa.Column('user_id', sa.UUID(), nullable=False),
        sa.Column('conversation_id', sa.UUID(), nullable=True),
        sa.Column('action', sa.String(length=50), nullable=False),
        sa.Column('message_count_at_action', sa.Integer(), nullable=True),
        sa.Column('audit_metadata', JSONB, nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False, server_default=sa.text('now()')),
        sa.ForeignKeyConstraint(['user_id'], ['users.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id')
    )

    # Indexes for conversation_audit_log
    op.create_index('ix_conversation_audit_log_user_id', 'conversation_audit_log', ['user_id'])
    op.create_index('ix_conversation_audit_log_action', 'conversation_audit_log', ['action'])
    op.create_index('ix_conversation_audit_log_user_created', 'conversation_audit_log', ['user_id', 'created_at'])

    # Modify message_token_summary to add conversation_id foreign key
    op.add_column(
        'message_token_summary',
        sa.Column('conversation_id', sa.UUID(), nullable=True)
    )
    op.create_foreign_key(
        'fk_message_token_summary_conversation_id',
        'message_token_summary',
        'conversations',
        ['conversation_id'],
        ['id'],
        ondelete='SET NULL'
    )
    op.create_index(
        'ix_message_token_summary_conversation_id',
        'message_token_summary',
        ['conversation_id']
    )


def downgrade() -> None:
    # Drop foreign key and column from message_token_summary
    op.drop_index('ix_message_token_summary_conversation_id', table_name='message_token_summary')
    op.drop_constraint('fk_message_token_summary_conversation_id', 'message_token_summary', type_='foreignkey')
    op.drop_column('message_token_summary', 'conversation_id')

    # Drop conversation_audit_log table
    op.drop_index('ix_conversation_audit_log_user_created', table_name='conversation_audit_log')
    op.drop_index('ix_conversation_audit_log_action', table_name='conversation_audit_log')
    op.drop_index('ix_conversation_audit_log_user_id', table_name='conversation_audit_log')
    op.drop_table('conversation_audit_log')

    # Drop conversation_messages table
    op.drop_index('ix_conversation_messages_conv_created', table_name='conversation_messages')
    op.drop_index('ix_conversation_messages_conversation_id', table_name='conversation_messages')
    op.drop_table('conversation_messages')

    # Drop conversations table
    op.drop_index('ix_conversations_user_created', table_name='conversations')
    op.drop_index('ix_conversations_deleted_at', table_name='conversations')
    op.drop_index('ix_conversations_user_id', table_name='conversations')
    op.drop_table('conversations')
