"""Encrypted phone ingestion/SMS archive and explicit independent consents.

Revision ID: 1c294a7e820f
Revises: b05f41e932c7

DDL is frozen here, never imported from evolving runtime models. Account soft
purge explicitly removes every new root; FKs also enforce tenant ownership.
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "1c294a7e820f"
down_revision: str | None = "b05f41e932c7"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("users", sa.Column("sms_preferences", postgresql.JSONB(), nullable=True))
    op.add_column("users", sa.Column("ingestion_key_encrypted", sa.Text(), nullable=True))
    op.execute("""
        CREATE TABLE ingestion_sources (
            user_id UUID NOT NULL,
            resource VARCHAR(32) NOT NULL,
            label_encrypted TEXT NOT NULL,
            revoked_at TIMESTAMP WITH TIME ZONE,
            last_seen_at TIMESTAMP WITH TIME ZONE,
            id UUID NOT NULL,
            created_at TIMESTAMP WITH TIME ZONE NOT NULL,
            updated_at TIMESTAMP WITH TIME ZONE NOT NULL,
            PRIMARY KEY (id),
            UNIQUE (user_id, id),
            FOREIGN KEY(user_id) REFERENCES users (id) ON DELETE CASCADE
        )
        """)
    op.execute("""
        CREATE INDEX ix_ingestion_sources_owner ON ingestion_sources (user_id, resource)
        """)
    op.execute("""
        CREATE TABLE sms_sender_blocks (
            user_id UUID NOT NULL,
            sender_hash VARCHAR(64) NOT NULL,
            sender_encrypted TEXT NOT NULL,
            id UUID NOT NULL,
            created_at TIMESTAMP WITH TIME ZONE NOT NULL,
            updated_at TIMESTAMP WITH TIME ZONE NOT NULL,
            PRIMARY KEY (id),
            CONSTRAINT uq_sms_owner_sender_block UNIQUE (user_id, sender_hash),
            FOREIGN KEY(user_id) REFERENCES users (id) ON DELETE CASCADE
        )
        """)
    op.execute("""
        CREATE TABLE ingestion_receipts (
            user_id UUID NOT NULL,
            source_id UUID NOT NULL,
            event_key VARCHAR(64) NOT NULL,
            payload_hash VARCHAR(64) NOT NULL,
            verdict VARCHAR(32) NOT NULL,
            filter_version INTEGER NOT NULL,
            id UUID NOT NULL,
            created_at TIMESTAMP WITH TIME ZONE NOT NULL,
            updated_at TIMESTAMP WITH TIME ZONE NOT NULL,
            PRIMARY KEY (id),
            UNIQUE (user_id, id),
            CONSTRAINT uq_ingestion_receipt_source_event UNIQUE (source_id, event_key),
            FOREIGN KEY(user_id, source_id) REFERENCES ingestion_sources (user_id, id) ON DELETE CASCADE,
            CONSTRAINT ck_ingestion_receipt_verdict CHECK (verdict IN ('stored','ignored_sensitive','ignored_sender','deleted')),
            FOREIGN KEY(user_id) REFERENCES users (id) ON DELETE CASCADE
        )
        """)
    op.execute("""
        CREATE TABLE ingestion_tokens (
            user_id UUID NOT NULL,
            source_id UUID NOT NULL,
            token_hash VARCHAR(64) NOT NULL,
            token_prefix VARCHAR(16) NOT NULL,
            scopes VARCHAR(48)[] NOT NULL,
            revoked_at TIMESTAMP WITH TIME ZONE,
            last_used_at TIMESTAMP WITH TIME ZONE,
            id UUID NOT NULL,
            created_at TIMESTAMP WITH TIME ZONE NOT NULL,
            updated_at TIMESTAMP WITH TIME ZONE NOT NULL,
            PRIMARY KEY (id),
            FOREIGN KEY(user_id, source_id) REFERENCES ingestion_sources (user_id, id) ON DELETE CASCADE,
            FOREIGN KEY(user_id) REFERENCES users (id) ON DELETE CASCADE,
            UNIQUE (token_hash)
        )
        """)
    op.execute("""
        CREATE TABLE ingestion_deliveries (
            user_id UUID NOT NULL,
            receipt_id UUID NOT NULL,
            destination_key VARCHAR(64) NOT NULL,
            device_id UUID,
            state VARCHAR(16) NOT NULL,
            attempts INTEGER NOT NULL,
            fence BIGINT NOT NULL,
            lease_owner UUID,
            lease_until TIMESTAMP WITH TIME ZONE,
            next_attempt_at TIMESTAMP WITH TIME ZONE,
            effect_id UUID,
            last_error_code VARCHAR(48),
            id UUID NOT NULL,
            created_at TIMESTAMP WITH TIME ZONE NOT NULL,
            updated_at TIMESTAMP WITH TIME ZONE NOT NULL,
            PRIMARY KEY (id),
            FOREIGN KEY(user_id, receipt_id) REFERENCES ingestion_receipts (user_id, id) ON DELETE CASCADE,
            CONSTRAINT uq_ingestion_delivery_destination UNIQUE (receipt_id, destination_key),
            CONSTRAINT ck_ingestion_delivery_state CHECK (state IN ('pending','sending','sent','failed','unknown','cancelled','expanded')),
            FOREIGN KEY(user_id) REFERENCES users (id) ON DELETE CASCADE
        )
        """)
    op.execute("""
        CREATE INDEX ix_ingestion_delivery_claim ON ingestion_deliveries (state, next_attempt_at)
        """)
    op.execute("""
        CREATE TABLE sms_messages (
            user_id UUID NOT NULL,
            receipt_id UUID NOT NULL,
            sender_encrypted TEXT NOT NULL,
            sender_hash VARCHAR(64) NOT NULL,
            body_encrypted TEXT NOT NULL,
            origin VARCHAR(32) NOT NULL,
            received_at TIMESTAMP WITH TIME ZONE NOT NULL,
            date_kind VARCHAR(16) NOT NULL,
            logical_bytes BIGINT NOT NULL,
            search_complete BOOLEAN NOT NULL,
            id UUID NOT NULL,
            created_at TIMESTAMP WITH TIME ZONE NOT NULL,
            updated_at TIMESTAMP WITH TIME ZONE NOT NULL,
            PRIMARY KEY (id),
            UNIQUE (user_id, id),
            FOREIGN KEY(user_id, receipt_id) REFERENCES ingestion_receipts (user_id, id) ON DELETE CASCADE,
            FOREIGN KEY(user_id) REFERENCES users (id) ON DELETE CASCADE,
            UNIQUE (receipt_id)
        )
        """)
    op.execute("""
        CREATE INDEX ix_sms_owner_date ON sms_messages (user_id, received_at, id)
        """)
    op.execute("""
        CREATE INDEX ix_sms_owner_sender_date ON sms_messages (user_id, sender_hash, received_at, id)
        """)
    op.execute("""
        CREATE TABLE sms_search_terms (
            user_id UUID NOT NULL,
            message_id UUID NOT NULL,
            term_hashes BYTEA[] NOT NULL,
            index_version INTEGER DEFAULT 1 NOT NULL,
            id UUID NOT NULL,
            created_at TIMESTAMP WITH TIME ZONE NOT NULL,
            updated_at TIMESTAMP WITH TIME ZONE NOT NULL,
            PRIMARY KEY (id),
            FOREIGN KEY(user_id, message_id) REFERENCES sms_messages (user_id, id) ON DELETE CASCADE,
            CONSTRAINT uq_sms_index_message UNIQUE (message_id),
            FOREIGN KEY(user_id) REFERENCES users (id) ON DELETE CASCADE
        )
        """)
    op.execute("""
        CREATE INDEX ix_sms_index_owner_message ON sms_search_terms (user_id, message_id)
        """)
    op.execute("""
        CREATE INDEX ix_sms_terms_gin ON sms_search_terms USING gin (term_hashes)
        """)


def downgrade() -> None:
    op.drop_table("sms_search_terms")
    op.drop_table("sms_messages")
    op.drop_table("ingestion_deliveries")
    op.drop_table("ingestion_tokens")
    op.drop_table("ingestion_receipts")
    op.drop_table("sms_sender_blocks")
    op.drop_table("ingestion_sources")
    op.drop_column("users", "ingestion_key_encrypted")
    op.drop_column("users", "sms_preferences")
