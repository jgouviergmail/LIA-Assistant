"""Add TTS cost columns to conversation_messages and aggregates on user_statistics.

Mirror of the STT migration (stt_messages_001 + stt_aggregates_user_pref_001)
applied to the assistant bubble.

Schema:
- conversation_messages: 5 nullable columns (NULL on user messages and on
  assistant messages whose TTS was free / not invoked):
    tts_provider           VARCHAR(50)
    tts_model              VARCHAR(100)
    tts_characters         INTEGER
    tts_cost_usd           NUMERIC(10,6)
    tts_cost_eur           NUMERIC(10,6)
    tts_usd_to_eur_rate    NUMERIC(10,6)
- Partial index on tts_provider WHERE tts_provider IS NOT NULL (TTS exports).
- user_statistics: 4 aggregate columns (lifetime + cycle, mirror STT):
    total_tts_characters   NUMERIC(12,0) NOT NULL DEFAULT 0
    total_tts_cost_eur     NUMERIC(12,6) NOT NULL DEFAULT 0
    cycle_tts_characters   NUMERIC(12,0) NOT NULL DEFAULT 0
    cycle_tts_cost_eur     NUMERIC(12,6) NOT NULL DEFAULT 0

Rationale:
- The cost driver is the assistant text (number of characters synthesised),
  attached to the assistant message bubble.
- ``tts_characters`` is a NUMERIC(12,0) for symmetry with the STT
  ``audio_seconds`` axis (also NUMERIC). Edge TTS rows stay NULL because the
  service only tracks paid providers.
- The cycle / total split mirrors STT exactly so the dashboard "Cost" card
  picks up TTS automatically through ``cycle_cost_eur``.

Revision ID: tts_aggregates_001
Revises: edge_provider_001
Create Date: 2026-05-07
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "tts_aggregates_001"
down_revision: str | None = "edge_provider_001"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # === conversation_messages: TTS cost detail ===
    op.add_column(
        "conversation_messages",
        sa.Column(
            "tts_provider",
            sa.String(length=50),
            nullable=True,
            comment=(
                "TTS provider that synthesised this assistant message "
                "(e.g. 'openai', 'elevenlabs'). NULL for user messages, free "
                "providers (Edge), or messages produced before TTS billing."
            ),
        ),
    )
    op.add_column(
        "conversation_messages",
        sa.Column(
            "tts_model",
            sa.String(length=100),
            nullable=True,
            comment="TTS model used (e.g. 'tts-1', 'eleven_turbo_v2_5'). NULL when no paid TTS was invoked.",
        ),
    )
    op.add_column(
        "conversation_messages",
        sa.Column(
            "tts_characters",
            sa.Integer(),
            nullable=True,
            comment="Number of characters synthesised (cost driver: TTS providers bill per character).",
        ),
    )
    op.add_column(
        "conversation_messages",
        sa.Column(
            "tts_cost_usd",
            sa.Numeric(precision=10, scale=6),
            nullable=True,
            comment="TTS cost in USD at synthesis time (computed via the in-memory pricing cache).",
        ),
    )
    op.add_column(
        "conversation_messages",
        sa.Column(
            "tts_cost_eur",
            sa.Numeric(precision=10, scale=6),
            nullable=True,
            comment="TTS cost in EUR at synthesis time.",
        ),
    )
    op.add_column(
        "conversation_messages",
        sa.Column(
            "tts_usd_to_eur_rate",
            sa.Numeric(precision=10, scale=6),
            nullable=True,
            comment="USD->EUR exchange rate used for the cost conversion (audit trail).",
        ),
    )

    # Partial index for TTS exports (small, only over rows with a provider set).
    op.create_index(
        "ix_conversation_messages_tts_provider",
        "conversation_messages",
        ["tts_provider"],
        postgresql_where=sa.text("tts_provider IS NOT NULL"),
    )

    # === user_statistics: TTS aggregates (lifetime + cycle) ===
    op.add_column(
        "user_statistics",
        sa.Column(
            "total_tts_characters",
            sa.Numeric(precision=12, scale=0),
            nullable=False,
            server_default="0",
            comment="Lifetime total of characters synthesised via paid TTS.",
        ),
    )
    op.add_column(
        "user_statistics",
        sa.Column(
            "total_tts_cost_eur",
            sa.Numeric(precision=12, scale=6),
            nullable=False,
            server_default="0",
            comment="Lifetime total cost in EUR attributable to paid TTS calls.",
        ),
    )
    op.add_column(
        "user_statistics",
        sa.Column(
            "cycle_tts_characters",
            sa.Numeric(precision=12, scale=0),
            nullable=False,
            server_default="0",
            comment="Current billing cycle characters synthesised via paid TTS.",
        ),
    )
    op.add_column(
        "user_statistics",
        sa.Column(
            "cycle_tts_cost_eur",
            sa.Numeric(precision=12, scale=6),
            nullable=False,
            server_default="0",
            comment="Current billing cycle cost in EUR attributable to paid TTS calls.",
        ),
    )


def downgrade() -> None:
    op.drop_column("user_statistics", "cycle_tts_cost_eur")
    op.drop_column("user_statistics", "cycle_tts_characters")
    op.drop_column("user_statistics", "total_tts_cost_eur")
    op.drop_column("user_statistics", "total_tts_characters")
    op.drop_index(
        "ix_conversation_messages_tts_provider",
        table_name="conversation_messages",
    )
    op.drop_column("conversation_messages", "tts_usd_to_eur_rate")
    op.drop_column("conversation_messages", "tts_cost_eur")
    op.drop_column("conversation_messages", "tts_cost_usd")
    op.drop_column("conversation_messages", "tts_characters")
    op.drop_column("conversation_messages", "tts_model")
    op.drop_column("conversation_messages", "tts_provider")
