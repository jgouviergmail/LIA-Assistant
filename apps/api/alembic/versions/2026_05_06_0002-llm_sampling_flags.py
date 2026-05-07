"""Add per-model sampling parameter flags.

Adds 4 boolean columns to llm_models declaring whether each model accepts
temperature, top_p, frequency_penalty, presence_penalty. Drives the
Configuration LLM admin UI conditional rendering — philosophy A: the UI
shows only what the API accepts.

Backfills the matrix for the 96 currently-active models.

Revision ID: llm_sampling_flags_001
Revises: llm_reasoning_overhaul_001
Create Date: 2026-05-06
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "llm_sampling_flags_001"
down_revision: str | None = "llm_reasoning_overhaul_001"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


# Per-model sampling support — encode the verbatim matrix from spec.
# Format: model_name -> (temp, top_p, freq, pres)
# Models not listed here default to (True, True, True, True) which is the
# safe permissive default (overwritten only when an explicit row exists).
SAMPLING_MATRIX: dict[str, tuple[bool, bool, bool, bool]] = {
    # ===== OpenAI reasoning (NO sampling) =====
    "o1": (False, False, False, False),
    "o1-mini": (False, False, False, False),
    "o1-pro": (False, False, False, False),
    "o3": (False, False, False, False),
    "o3-mini": (False, False, False, False),
    "o3-pro": (False, False, False, False),
    "o3-deep-research": (False, False, False, False),
    "o4-mini": (False, False, False, False),
    "o4-mini-deep-research": (False, False, False, False),
    "gpt-5": (False, False, False, False),
    "gpt-5-mini": (False, False, False, False),
    "gpt-5-nano": (False, False, False, False),
    "gpt-5-pro": (False, False, False, False),
    "gpt-5-codex": (False, False, False, False),
    "gpt-5.1": (False, False, False, False),
    "gpt-5.1-codex": (False, False, False, False),
    "gpt-5.1-codex-max": (False, False, False, False),
    "gpt-5.1-codex-mini": (False, False, False, False),
    "gpt-5.2": (False, False, False, False),
    "gpt-5.2-codex": (False, False, False, False),
    "gpt-5.2-pro": (False, False, False, False),
    "gpt-5.3-codex": (False, False, False, False),
    "gpt-5.4": (False, False, False, False),
    "gpt-5.4-mini": (False, False, False, False),
    # OpenAI chat-latest = treated as plain chat models (sampling supported)
    "gpt-5-chat-latest": (True, True, True, True),
    "gpt-5.1-chat-latest": (True, True, True, True),
    "gpt-5.2-chat-latest": (True, True, True, True),
    "gpt-5.3-chat-latest": (True, True, True, True),
    "gpt-5-search-api": (True, True, True, True),
    # OpenAI non-reasoning chat
    "gpt-4o": (True, True, True, True),
    "gpt-4o-2024-05-13": (True, True, True, True),
    "gpt-4o-mini": (True, True, True, True),
    "gpt-4o-audio-preview": (True, True, True, True),
    "gpt-4o-mini-audio-preview": (True, True, True, True),
    "gpt-4o-realtime-preview": (True, True, True, True),
    "gpt-4o-mini-realtime-preview": (True, True, True, True),
    "gpt-4o-search-preview": (True, True, True, True),
    "gpt-4o-mini-search-preview": (True, True, True, True),
    "gpt-4.1": (True, True, True, True),
    "gpt-4.1-mini": (True, True, True, True),
    "gpt-4.1-nano": (True, True, True, True),
    "gpt-realtime": (True, True, True, True),
    "gpt-realtime-1.5": (True, True, True, True),
    "gpt-realtime-mini": (True, True, True, True),
    "gpt-audio": (True, True, True, True),
    "gpt-audio-1.5": (True, True, True, True),
    "gpt-audio-mini": (True, True, True, True),
    "computer-use-preview": (True, True, True, True),
    # OpenAI special (no sampling — image / embeddings)
    "chatgpt-image-latest": (False, False, False, False),
    "text-embedding-3-large": (False, False, False, False),
    "text-embedding-3-small": (False, False, False, False),
    "text-embedding-ada-002": (False, False, False, False),
    # ===== Anthropic 4.5+ (temperature only — no top_p, no penalties) =====
    "claude-opus-4.5": (True, False, False, False),
    "claude-opus-4.6": (True, False, False, False),
    "claude-sonnet-4.6": (True, False, False, False),
    "claude-haiku-4.5": (True, False, False, False),
    # ===== DeepSeek =====
    "deepseek-chat": (True, True, True, True),
    "deepseek-reasoner": (False, False, False, False),
    "deepseek-v4-flash": (True, True, True, True),
    "deepseek-v4-pro": (True, True, True, True),
    # ===== Gemini chat (no penalties) =====
    "gemini-2.0-flash": (True, True, False, False),
    "gemini-2.0-flash-001": (True, True, False, False),
    "gemini-2.0-flash-exp": (True, True, False, False),
    "gemini-2.0-flash-lite": (True, True, False, False),
    "gemini-2.0-flash-lite-001": (True, True, False, False),
    "gemini-2.0-flash-live-001": (True, True, False, False),
    "gemini-2.5-flash": (True, True, False, False),
    "gemini-2.5-flash-preview-09-2025": (True, True, False, False),
    "gemini-2.5-flash-lite": (True, True, False, False),
    "gemini-2.5-flash-lite-preview-09-2025": (True, True, False, False),
    "gemini-2.5-pro": (True, True, False, False),
    "gemini-3-flash-preview": (True, True, False, False),
    "gemini-3-pro-preview": (True, True, False, False),
    "gemini-3.1-flash-lite-preview": (True, True, False, False),
    "gemini-3.1-pro-preview": (True, True, False, False),
    # Gemini image/audio/tts/embedding — no sampling
    "gemini-2.0-flash-preview-image-generation": (False, False, False, False),
    "gemini-2.5-flash-image": (False, False, False, False),
    "gemini-2.5-flash-image-preview": (False, False, False, False),
    "gemini-2.5-flash-native-audio-preview-09-2025": (False, False, False, False),
    "gemini-2.5-flash-preview-tts": (False, False, False, False),
    "gemini-2.5-pro-preview-tts": (False, False, False, False),
    "gemini-3-pro-image-preview": (False, False, False, False),
    "embedding-001": (False, False, False, False),
    "gemini-embedding-001": (False, False, False, False),
    "text-embedding-004": (False, False, False, False),
    # ===== Qwen (no frequency_penalty) =====
    "qwen2.5": (True, True, False, True),
    "qwen3-max": (True, True, False, True),
    "qwen3.5-plus": (True, True, False, True),
    "qwen3.5-flash": (True, True, False, True),
    "qwen3.6-plus": (True, True, False, True),
    # ===== Perplexity =====
    "sonar": (True, True, True, True),
    "sonar-pro": (True, True, True, True),
    "sonar-reasoning-pro": (True, True, True, True),
    "sonar-deep-research": (True, True, True, True),
    # ===== Ollama =====
    "llama3.2": (True, True, True, True),
    "mistral": (True, True, True, True),
}


def upgrade() -> None:
    bind = op.get_bind()

    # 1. Add columns (default = True for safety; backfill overrides immediately).
    op.add_column(
        "llm_models",
        sa.Column("supports_temperature", sa.Boolean, nullable=False, server_default=sa.true()),
    )
    op.add_column(
        "llm_models",
        sa.Column("supports_top_p", sa.Boolean, nullable=False, server_default=sa.true()),
    )
    op.add_column(
        "llm_models",
        sa.Column(
            "supports_frequency_penalty",
            sa.Boolean,
            nullable=False,
            server_default=sa.true(),
        ),
    )
    op.add_column(
        "llm_models",
        sa.Column(
            "supports_presence_penalty",
            sa.Boolean,
            nullable=False,
            server_default=sa.true(),
        ),
    )

    # 2. Backfill from matrix.
    for model_name, (temp, top_p, freq, pres) in SAMPLING_MATRIX.items():
        bind.execute(sa.text("""
                UPDATE llm_models SET
                    supports_temperature = :temp,
                    supports_top_p = :top_p,
                    supports_frequency_penalty = :freq,
                    supports_presence_penalty = :pres
                WHERE model_name = :name
                """).bindparams(temp=temp, top_p=top_p, freq=freq, pres=pres, name=model_name))

    # 3. Drop the server defaults (we want explicit values going forward).
    op.alter_column("llm_models", "supports_temperature", server_default=None)
    op.alter_column("llm_models", "supports_top_p", server_default=None)
    op.alter_column("llm_models", "supports_frequency_penalty", server_default=None)
    op.alter_column("llm_models", "supports_presence_penalty", server_default=None)

    # 4. Reconcile is_reasoning_model with reasoning_widget. The pre-PR seed
    #    initialised every row with is_reasoning_model=false; the previous
    #    migration (llm_reasoning_overhaul_001) populated reasoning_widget but
    #    forgot to refresh this flag. Fix here so the two stay in sync.
    #
    #    Rule:
    #      is_reasoning_model = (reasoning_widget != 'none') OR
    #                           model_name = 'deepseek-reasoner'
    #
    #    Special case for deepseek-reasoner: reasoning is always-on (no level
    #    control), so its widget is 'none' but it IS a reasoning model.
    op.execute("""
        UPDATE llm_models SET is_reasoning_model = TRUE
        WHERE reasoning_widget != 'none' OR model_name = 'deepseek-reasoner'
        """)
    op.execute("""
        UPDATE llm_models SET is_reasoning_model = FALSE
        WHERE reasoning_widget = 'none' AND model_name != 'deepseek-reasoner'
        """)


def downgrade() -> None:
    op.drop_column("llm_models", "supports_presence_penalty")
    op.drop_column("llm_models", "supports_frequency_penalty")
    op.drop_column("llm_models", "supports_top_p")
    op.drop_column("llm_models", "supports_temperature")
