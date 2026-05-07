"""Add STT cost columns to conversation_messages.

Schema:
- Adds 5 nullable columns on conversation_messages to attach STT cost data
  to the user-bubble (the message that was transcribed) when the user has
  opted into a remote STT provider (e.g. ElevenLabs Scribe):
    stt_provider                 VARCHAR(50)   NULL
    stt_audio_duration_seconds   NUMERIC(10,2) NULL
    stt_cost_usd                 NUMERIC(10,6) NULL
    stt_cost_eur                 NUMERIC(10,6) NULL
    stt_usd_to_eur_rate          NUMERIC(10,6) NULL
- Adds a partial index on stt_provider (WHERE stt_provider IS NOT NULL)
  to speed up STT usage exports without bloating the base index.

Rationale:
- Costs are attached to the user message that triggered the STT call (the
  audio is the cost driver). Pattern is consistent with `message_metadata`
  JSONB already living on the same row. All columns are NULL for assistant
  messages and for user messages produced by the local Sherpa pipeline
  (which is free).

Revision ID: stt_messages_001
Revises: pricing_unit_rename_001
Create Date: 2026-05-07
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "stt_messages_001"
down_revision: str | None = "pricing_unit_rename_001"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "conversation_messages",
        sa.Column(
            "stt_provider",
            sa.String(length=50),
            nullable=True,
            comment="STT provider that produced this user message (e.g. 'elevenlabs'). NULL for assistant messages or local Sherpa transcriptions.",
        ),
    )
    op.add_column(
        "conversation_messages",
        sa.Column(
            "stt_audio_duration_seconds",
            sa.Numeric(precision=10, scale=2),
            nullable=True,
            comment="Duration of the audio segment transcribed, in seconds (authoritative value returned by the STT provider).",
        ),
    )
    op.add_column(
        "conversation_messages",
        sa.Column(
            "stt_cost_usd",
            sa.Numeric(precision=10, scale=6),
            nullable=True,
            comment="STT cost in USD at the time of the call (computed from llm_model_pricing per pricing_unit).",
        ),
    )
    op.add_column(
        "conversation_messages",
        sa.Column(
            "stt_cost_eur",
            sa.Numeric(precision=10, scale=6),
            nullable=True,
            comment="STT cost in EUR at the time of the call.",
        ),
    )
    op.add_column(
        "conversation_messages",
        sa.Column(
            "stt_usd_to_eur_rate",
            sa.Numeric(precision=10, scale=6),
            nullable=True,
            comment="USD->EUR exchange rate used for the cost conversion (audit trail).",
        ),
    )

    # Partial index for STT exports (small, only over rows with a provider set).
    op.create_index(
        "ix_conversation_messages_stt_provider",
        "conversation_messages",
        ["stt_provider"],
        postgresql_where=sa.text("stt_provider IS NOT NULL"),
    )


def downgrade() -> None:
    op.drop_index(
        "ix_conversation_messages_stt_provider",
        table_name="conversation_messages",
    )
    op.drop_column("conversation_messages", "stt_usd_to_eur_rate")
    op.drop_column("conversation_messages", "stt_cost_eur")
    op.drop_column("conversation_messages", "stt_cost_usd")
    op.drop_column("conversation_messages", "stt_audio_duration_seconds")
    op.drop_column("conversation_messages", "stt_provider")
