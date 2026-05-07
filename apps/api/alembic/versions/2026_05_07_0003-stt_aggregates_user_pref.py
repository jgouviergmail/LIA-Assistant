"""Add STT aggregates to user_statistics + voice_stt_mode preference on users.

Schema:
- user_statistics gets 4 new columns to track STT usage (lifetime + cycle):
    total_stt_audio_seconds   NUMERIC(12,2) NOT NULL DEFAULT 0
    total_stt_cost_eur        NUMERIC(12,6) NOT NULL DEFAULT 0
    cycle_stt_audio_seconds   NUMERIC(12,2) NOT NULL DEFAULT 0
    cycle_stt_cost_eur        NUMERIC(12,6) NOT NULL DEFAULT 0
- users gets the voice_stt_mode preference (local | remote, default 'local').
  The choice is read at /voice/ticket emission time and embedded in the
  WebSocket ticket so the /ws/audio handler routes to the correct STT
  service without re-querying the DB.

Rationale:
- STT cost contributes to user_statistics.cycle_cost_eur via add_stt_usage()
  in the StatisticsService (cf. plan §9). The dedicated stt_* columns let us
  surface STT-specific volume in the dashboard and exports without losing the
  aggregated cost view.
- voice_stt_mode lives next to voice_mode_enabled / voice_enabled on the
  users table for symmetry.

Revision ID: stt_aggregates_user_pref_001
Revises: stt_messages_001
Create Date: 2026-05-07
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "stt_aggregates_user_pref_001"
down_revision: str | None = "stt_messages_001"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # === user_statistics: STT aggregates ===
    op.add_column(
        "user_statistics",
        sa.Column(
            "total_stt_audio_seconds",
            sa.Numeric(precision=12, scale=2),
            nullable=False,
            server_default="0",
            comment="Lifetime total of audio seconds transcribed via remote STT.",
        ),
    )
    op.add_column(
        "user_statistics",
        sa.Column(
            "total_stt_cost_eur",
            sa.Numeric(precision=12, scale=6),
            nullable=False,
            server_default="0",
            comment="Lifetime total cost in EUR attributable to remote STT calls.",
        ),
    )
    op.add_column(
        "user_statistics",
        sa.Column(
            "cycle_stt_audio_seconds",
            sa.Numeric(precision=12, scale=2),
            nullable=False,
            server_default="0",
            comment="Current billing cycle audio seconds transcribed via remote STT.",
        ),
    )
    op.add_column(
        "user_statistics",
        sa.Column(
            "cycle_stt_cost_eur",
            sa.Numeric(precision=12, scale=6),
            nullable=False,
            server_default="0",
            comment="Current billing cycle cost in EUR attributable to remote STT calls.",
        ),
    )

    # === users: voice_stt_mode preference ===
    op.add_column(
        "users",
        sa.Column(
            "voice_stt_mode",
            sa.String(length=20),
            nullable=False,
            server_default="local",
            comment=(
                "User preference for the STT provider when voice_mode_enabled=true. "
                "'local' (default) = on-server Sherpa-onnx Whisper. "
                "'remote' = ElevenLabs Scribe (paid, billed per audio duration)."
            ),
        ),
    )


def downgrade() -> None:
    op.drop_column("users", "voice_stt_mode")
    op.drop_column("user_statistics", "cycle_stt_cost_eur")
    op.drop_column("user_statistics", "cycle_stt_audio_seconds")
    op.drop_column("user_statistics", "total_stt_cost_eur")
    op.drop_column("user_statistics", "total_stt_audio_seconds")
