"""LLM reasoning_effort overhaul.

Schema:
- Adds llm_models.kind, reasoning_widget, reasoning_enum_values,
  reasoning_budget_range, reasoning_doc_i18n_key.
- Converts llm_config_overrides.reasoning_effort: VARCHAR(20) -> JSONB.

Data:
- Backfills new columns on existing rows from REASONING_MATRIX (embedded).
- Cleans incompatible reasoning_effort values from llm_config_overrides
  to NULL (admin reconfigures via UI post-deploy).
- Deletes 25 obsolete model rows (and their pricing + override entries
  via FK-aware ordering).

Downgrade limitation:
- Schema changes are reversible.
- Deleted models are NOT restored. Re-running the seeds (or restoring
  from backup) is the only recovery path. Documented intentionally:
  none of the deleted models is in active use.

Revision ID: llm_reasoning_overhaul_001
Revises: journals_stratified_001
Create Date: 2026-05-06
"""

from __future__ import annotations

import json
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import JSONB

# revision identifiers, used by Alembic.
revision: str = "llm_reasoning_overhaul_001"
down_revision: str | None = "journals_stratified_001"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


# ============================================================================
# Embedded matrix (mirrors llm_pricing_seed.sql)
# Format: model_name -> (kind, widget, enum_values_or_None, budget_range_or_None, doc_key_or_None)
# ============================================================================
REASONING_MATRIX: dict[str, tuple[str, str, list[str] | None, dict | None, str | None]] = {
    # OpenAI gpt-5 family
    "gpt-5": ("chat", "enum", ["minimal", "low", "medium", "high"], None, "openai_gpt5"),
    "gpt-5-mini": ("chat", "enum", ["minimal", "low", "medium", "high"], None, "openai_gpt5"),
    "gpt-5-nano": ("chat", "enum", ["minimal", "low", "medium", "high"], None, "openai_gpt5"),
    "gpt-5-pro": ("chat", "enum", ["high"], None, "openai_gpt5_pro"),
    "gpt-5-codex": ("chat", "enum", ["low", "medium", "high"], None, "openai_gpt5_codex"),
    "gpt-5-chat-latest": ("chat", "none", None, None, None),
    "gpt-5-search-api": ("chat", "none", None, None, None),
    # OpenAI gpt-5.1
    "gpt-5.1": ("chat", "enum", ["none", "low", "medium", "high"], None, "openai_gpt5_1"),
    "gpt-5.1-codex": ("chat", "enum", ["low", "medium", "high"], None, "openai_gpt5_1_codex"),
    "gpt-5.1-codex-max": (
        "chat",
        "enum",
        ["low", "medium", "high", "xhigh"],
        None,
        "openai_gpt5_1_codex_max",
    ),
    "gpt-5.1-codex-mini": (
        "chat",
        "enum",
        ["low", "medium", "high"],
        None,
        "openai_gpt5_1_codex",
    ),
    "gpt-5.1-chat-latest": ("chat", "none", None, None, None),
    # OpenAI gpt-5.2
    "gpt-5.2": (
        "chat",
        "enum",
        ["none", "low", "medium", "high", "xhigh"],
        None,
        "openai_gpt5_2",
    ),
    "gpt-5.2-codex": (
        "chat",
        "enum",
        ["low", "medium", "high", "xhigh"],
        None,
        "openai_gpt5_2_codex",
    ),
    "gpt-5.2-pro": (
        "chat",
        "enum",
        ["medium", "high", "xhigh"],
        None,
        "openai_gpt5_2_pro",
    ),
    "gpt-5.2-chat-latest": ("chat", "enum", ["medium"], None, "openai_gpt5_2_chat_latest"),
    # OpenAI gpt-5.3 / 5.4
    "gpt-5.3-codex": (
        "chat",
        "enum",
        ["low", "medium", "high", "xhigh"],
        None,
        "openai_gpt5_3_codex",
    ),
    "gpt-5.3-chat-latest": ("chat", "none", None, None, None),
    "gpt-5.4": (
        "chat",
        "enum",
        ["none", "low", "medium", "high", "xhigh"],
        None,
        "openai_gpt5_4",
    ),
    "gpt-5.4-mini": (
        "chat",
        "enum",
        ["none", "low", "medium", "high", "xhigh"],
        None,
        "openai_gpt5_4_mini",
    ),
    # OpenAI o-series
    "o1": ("chat", "enum", ["low", "medium", "high"], None, "openai_o_series"),
    "o1-mini": ("chat", "none", None, None, None),
    "o1-pro": ("chat", "enum", ["low", "medium", "high"], None, "openai_o_series"),
    "o3": ("chat", "enum", ["low", "medium", "high"], None, "openai_o_series"),
    "o3-mini": ("chat", "enum", ["low", "medium", "high"], None, "openai_o_series"),
    "o3-pro": ("chat", "enum", ["low", "medium", "high"], None, "openai_o_series"),
    "o3-deep-research": ("chat", "none", None, None, None),
    "o4-mini": ("chat", "enum", ["low", "medium", "high"], None, "openai_o_series"),
    "o4-mini-deep-research": ("chat", "none", None, None, None),
    # OpenAI gpt-4o family
    "gpt-4o": ("chat", "none", None, None, None),
    "gpt-4o-2024-05-13": ("chat", "none", None, None, None),
    "gpt-4o-mini": ("chat", "none", None, None, None),
    "gpt-4o-audio-preview": ("audio", "none", None, None, None),
    "gpt-4o-mini-audio-preview": ("audio", "none", None, None, None),
    "gpt-4o-realtime-preview": ("realtime", "none", None, None, None),
    "gpt-4o-mini-realtime-preview": ("realtime", "none", None, None, None),
    "gpt-4o-search-preview": ("chat", "none", None, None, None),
    "gpt-4o-mini-search-preview": ("chat", "none", None, None, None),
    # OpenAI gpt-4.1 family
    "gpt-4.1": ("chat", "none", None, None, None),
    "gpt-4.1-mini": ("chat", "none", None, None, None),
    "gpt-4.1-nano": ("chat", "none", None, None, None),
    # OpenAI realtime / audio standalone
    "gpt-realtime": ("realtime", "none", None, None, None),
    "gpt-realtime-1.5": ("realtime", "none", None, None, None),
    "gpt-realtime-mini": ("realtime", "none", None, None, None),
    "gpt-audio": ("audio", "none", None, None, None),
    "gpt-audio-1.5": ("audio", "none", None, None, None),
    "gpt-audio-mini": ("audio", "none", None, None, None),
    # OpenAI special
    "computer-use-preview": ("chat", "none", None, None, None),
    "chatgpt-image-latest": ("image", "none", None, None, None),
    "text-embedding-3-large": ("embedding", "none", None, None, None),
    "text-embedding-3-small": ("embedding", "none", None, None, None),
    "text-embedding-ada-002": ("embedding", "none", None, None, None),
    # Anthropic kept (4)
    "claude-opus-4.5": ("chat", "enum", ["low", "medium", "high"], None, "anthropic_4_5"),
    "claude-opus-4.6": (
        "chat",
        "enum",
        ["low", "medium", "high", "max"],
        None,
        "anthropic_4_6",
    ),
    "claude-sonnet-4.6": (
        "chat",
        "enum",
        ["low", "medium", "high"],
        None,
        "anthropic_sonnet_4_6",
    ),
    "claude-haiku-4.5": ("chat", "none", None, None, None),
    # DeepSeek
    "deepseek-chat": ("chat", "none", None, None, None),
    "deepseek-reasoner": ("chat", "none", None, None, None),
    "deepseek-v4-flash": ("chat", "enum", ["off", "high", "max"], None, "deepseek_v4"),
    "deepseek-v4-pro": ("chat", "enum", ["off", "high", "max"], None, "deepseek_v4"),
    # Gemini 2.0 family
    "gemini-2.0-flash": ("chat", "none", None, None, None),
    "gemini-2.0-flash-001": ("chat", "none", None, None, None),
    "gemini-2.0-flash-exp": ("chat", "none", None, None, None),
    "gemini-2.0-flash-lite": ("chat", "none", None, None, None),
    "gemini-2.0-flash-lite-001": ("chat", "none", None, None, None),
    "gemini-2.0-flash-live-001": ("chat", "none", None, None, None),
    "gemini-2.0-flash-preview-image-generation": ("image", "none", None, None, None),
    # Gemini 2.5 family
    "gemini-2.5-flash": (
        "chat",
        "budget_int",
        None,
        {"min": 1, "max": 24576, "off_sentinel": 0, "dynamic_sentinel": -1},
        "gemini_2_5",
    ),
    "gemini-2.5-flash-preview-09-2025": ("chat", "none", None, None, None),
    "gemini-2.5-flash-lite": (
        "chat",
        "budget_int",
        None,
        {"min": 512, "max": 24576, "off_sentinel": 0, "dynamic_sentinel": -1},
        "gemini_2_5_lite",
    ),
    "gemini-2.5-flash-lite-preview-09-2025": ("chat", "none", None, None, None),
    "gemini-2.5-flash-image": ("image", "none", None, None, None),
    "gemini-2.5-flash-image-preview": ("image", "none", None, None, None),
    "gemini-2.5-flash-native-audio-preview-09-2025": ("audio", "none", None, None, None),
    "gemini-2.5-flash-preview-tts": ("tts", "none", None, None, None),
    "gemini-2.5-pro-preview-tts": ("tts", "none", None, None, None),
    "gemini-2.5-pro": (
        "chat",
        "budget_int",
        None,
        {"min": 128, "max": 32768, "dynamic_sentinel": -1},
        "gemini_2_5_pro",
    ),
    # Gemini 3.x
    "gemini-3-flash-preview": (
        "chat",
        "enum",
        ["minimal", "low", "medium", "high"],
        None,
        "gemini_3_x_flash",
    ),
    "gemini-3-pro-preview": (
        "chat",
        "enum",
        ["low", "medium", "high"],
        None,
        "gemini_3_x_pro",
    ),
    "gemini-3-pro-image-preview": ("image", "none", None, None, None),
    "gemini-3.1-flash-lite-preview": (
        "chat",
        "enum",
        ["minimal", "low", "medium", "high"],
        None,
        "gemini_3_x_flash",
    ),
    "gemini-3.1-pro-preview": (
        "chat",
        "enum",
        ["low", "medium", "high"],
        None,
        "gemini_3_x_pro",
    ),
    # Gemini embeddings
    "embedding-001": ("embedding", "none", None, None, None),
    "gemini-embedding-001": ("embedding", "none", None, None, None),
    "text-embedding-004": ("embedding", "none", None, None, None),
    # Qwen
    "qwen2.5": ("chat", "none", None, None, None),
    "qwen3-max": ("chat", "toggle_budget", None, {"min": 0, "max": 32768}, "qwen3_max"),
    "qwen3.5-plus": ("chat", "toggle_budget", None, {"min": 0, "max": 32768}, "qwen3_5"),
    "qwen3.5-flash": ("chat", "toggle_budget", None, {"min": 0, "max": 32768}, "qwen3_5"),
    "qwen3.6-plus": ("chat", "toggle_budget", None, {"min": 0, "max": 32768}, "qwen3_5"),
    # Perplexity
    "sonar": ("chat", "none", None, None, None),
    "sonar-pro": ("chat", "none", None, None, None),
    "sonar-reasoning-pro": ("chat", "none", None, None, None),
    "sonar-deep-research": (
        "chat",
        "enum",
        ["low", "medium", "high"],
        None,
        "perplexity_deep",
    ),
    # Ollama
    "llama3.2": ("chat", "none", None, None, None),
    "mistral": ("chat", "none", None, None, None),
}


DELETED_MODELS: list[str] = [
    # OpenAI fictional + deprecated (8)
    "gpt-4.1-mini-mini",
    "gpt-4.1-mini-mini-audio-preview",
    "gpt-4.1-mini-mini-realtime-preview",
    "gpt-4.1-mini-mini-search-preview",
    "gpt-4.1-mini-realtime-preview",
    "gpt-4.1-mini-audio-preview",
    "gpt-4.1-mini-search-preview",
    "codex-mini-latest",
    # Anthropic aggressive scope (17)
    "claude-opus-3",
    "claude-opus-4",
    "claude-opus-4-1",
    "claude-opus-4.1",
    "claude-opus-4-5",
    "claude-opus-4-6",
    "claude-sonnet-3-7",
    "claude-sonnet-3.7",
    "claude-sonnet-4",
    "claude-sonnet-4-5",
    "claude-sonnet-4.5",
    "claude-sonnet-4-6",
    "claude-haiku-3",
    "claude-haiku-3-5",
    "claude-haiku-3.5",
    "claude-3-5-haiku-latest",
    "claude-haiku-4-5",
]


def upgrade() -> None:
    bind = op.get_bind()

    # === 1. Create new PostgreSQL ENUM types ===
    op.execute(
        "CREATE TYPE llm_model_kind_enum AS ENUM "
        "('chat','image','audio','realtime','tts','embedding')"
    )
    op.execute(
        "CREATE TYPE llm_reasoning_widget_enum AS ENUM "
        "('none','enum','budget_int','toggle_budget')"
    )

    # === 2. Add new columns to llm_models (NULLABLE for backfill) ===
    op.add_column(
        "llm_models",
        sa.Column(
            "kind",
            sa.Enum(
                "chat",
                "image",
                "audio",
                "realtime",
                "tts",
                "embedding",
                name="llm_model_kind_enum",
                create_type=False,
            ),
            nullable=True,
        ),
    )
    op.add_column(
        "llm_models",
        sa.Column(
            "reasoning_widget",
            sa.Enum(
                "none",
                "enum",
                "budget_int",
                "toggle_budget",
                name="llm_reasoning_widget_enum",
                create_type=False,
            ),
            nullable=True,
        ),
    )
    op.add_column("llm_models", sa.Column("reasoning_enum_values", JSONB, nullable=True))
    op.add_column("llm_models", sa.Column("reasoning_budget_range", JSONB, nullable=True))
    op.add_column("llm_models", sa.Column("reasoning_doc_i18n_key", sa.String(100), nullable=True))

    # === 3. Backfill kind + reasoning_widget + values from REASONING_MATRIX ===
    for model_name, (kind, widget, enum_values, budget_range, doc_key) in REASONING_MATRIX.items():
        bind.execute(
            sa.text("""
                UPDATE llm_models SET
                    kind = CAST(:kind AS llm_model_kind_enum),
                    reasoning_widget = CAST(:widget AS llm_reasoning_widget_enum),
                    reasoning_enum_values = CAST(:enum_values AS jsonb),
                    reasoning_budget_range = CAST(:budget_range AS jsonb),
                    reasoning_doc_i18n_key = :doc_key
                WHERE model_name = :name
                """).bindparams(
                kind=kind,
                widget=widget,
                enum_values=json.dumps(enum_values) if enum_values is not None else None,
                budget_range=json.dumps(budget_range) if budget_range is not None else None,
                doc_key=doc_key,
                name=model_name,
            )
        )

    # === 4. Default any unmatched rows (rows present in DB but not in matrix) ===
    # Safe defaults: kind='chat', widget='none' (no reasoning UI surfaced).
    op.execute("UPDATE llm_models SET kind = 'chat'::llm_model_kind_enum WHERE kind IS NULL")
    op.execute(
        "UPDATE llm_models SET reasoning_widget = 'none'::llm_reasoning_widget_enum "
        "WHERE reasoning_widget IS NULL"
    )

    # === 5. Convert llm_config_overrides.reasoning_effort: VARCHAR -> JSONB ===
    op.execute("""
        ALTER TABLE llm_config_overrides
        ALTER COLUMN reasoning_effort TYPE jsonb
        USING CASE
            WHEN reasoning_effort IS NULL THEN NULL
            ELSE jsonb_build_object('effort', reasoning_effort)
        END
        """)

    # === 6. Cleanup invalid overrides against the new matrix ===
    # 6a. widget=none -> any non-NULL reasoning_effort is invalid
    op.execute("""
        UPDATE llm_config_overrides AS lco
        SET reasoning_effort = NULL
        FROM llm_models AS lm
        WHERE lm.model_name = lco.model
          AND lm.reasoning_widget = 'none'
          AND lco.reasoning_effort IS NOT NULL
        """)
    # 6b. widget=enum -> value.effort must be in enum_values
    op.execute("""
        UPDATE llm_config_overrides AS lco
        SET reasoning_effort = NULL
        FROM llm_models AS lm
        WHERE lm.model_name = lco.model
          AND lm.reasoning_widget = 'enum'
          AND lco.reasoning_effort IS NOT NULL
          AND (
              NOT (lco.reasoning_effort ? 'effort')
              OR NOT (lco.reasoning_effort->>'effort' = ANY(
                  SELECT jsonb_array_elements_text(lm.reasoning_enum_values)))
          )
        """)
    # 6c. widget=budget_int -> budget must be in range or sentinel
    op.execute("""
        UPDATE llm_config_overrides AS lco
        SET reasoning_effort = NULL
        FROM llm_models AS lm
        WHERE lm.model_name = lco.model
          AND lm.reasoning_widget = 'budget_int'
          AND lco.reasoning_effort IS NOT NULL
          AND (
              NOT (lco.reasoning_effort ? 'budget')
              OR NOT (
                  (lco.reasoning_effort->>'budget')::int = COALESCE((lm.reasoning_budget_range->>'off_sentinel')::int, -99999)
                  OR (lco.reasoning_effort->>'budget')::int = COALESCE((lm.reasoning_budget_range->>'dynamic_sentinel')::int, -99999)
                  OR ((lco.reasoning_effort->>'budget')::int BETWEEN
                      (lm.reasoning_budget_range->>'min')::int AND
                      (lm.reasoning_budget_range->>'max')::int)
              )
          )
        """)
    # 6d. widget=toggle_budget -> shape match required
    op.execute("""
        UPDATE llm_config_overrides AS lco
        SET reasoning_effort = NULL
        FROM llm_models AS lm
        WHERE lm.model_name = lco.model
          AND lm.reasoning_widget = 'toggle_budget'
          AND lco.reasoning_effort IS NOT NULL
          AND (
              NOT (lco.reasoning_effort ? 'enabled')
              OR (
                  (lco.reasoning_effort->>'enabled')::boolean = true
                  AND lco.reasoning_effort ? 'budget'
                  AND (lco.reasoning_effort->>'budget') IS NOT NULL
                  AND NOT ((lco.reasoning_effort->>'budget')::int BETWEEN
                      (lm.reasoning_budget_range->>'min')::int AND
                      (lm.reasoning_budget_range->>'max')::int)
              )
          )
        """)

    # === 7. Delete obsolete model rows (FK-aware order) ===
    bind.execute(
        sa.text("DELETE FROM llm_config_overrides WHERE model = ANY(:m)").bindparams(
            m=DELETED_MODELS
        )
    )
    bind.execute(
        sa.text(
            "DELETE FROM llm_model_pricing "
            "WHERE model_id IN (SELECT id FROM llm_models WHERE model_name = ANY(:m))"
        ).bindparams(m=DELETED_MODELS)
    )
    bind.execute(
        sa.text("DELETE FROM llm_models WHERE model_name = ANY(:m)").bindparams(m=DELETED_MODELS)
    )

    # === 8. NOT NULL on the new required columns ===
    op.alter_column("llm_models", "kind", nullable=False)
    op.alter_column("llm_models", "reasoning_widget", nullable=False)


def downgrade() -> None:
    """Schema downgrade only. Deleted models are NOT restored.

    Re-running the seeds (or restoring DB from backup) is the only
    recovery path for the 25 obsolete models removed by upgrade().
    Documented intentionally: none of those models was in active use.
    """
    # Reverse JSONB -> VARCHAR (extract 'effort' key; widget='enum' rows survive,
    # other shapes are coerced to NULL since VARCHAR can't carry the int/bool data).
    op.execute("""
        ALTER TABLE llm_config_overrides
        ALTER COLUMN reasoning_effort TYPE varchar(20)
        USING CASE
            WHEN reasoning_effort IS NULL THEN NULL
            WHEN reasoning_effort ? 'effort' THEN reasoning_effort->>'effort'
            ELSE NULL
        END
        """)

    # Drop new columns
    op.drop_column("llm_models", "reasoning_doc_i18n_key")
    op.drop_column("llm_models", "reasoning_budget_range")
    op.drop_column("llm_models", "reasoning_enum_values")
    op.drop_column("llm_models", "reasoning_widget")
    op.drop_column("llm_models", "kind")

    # Drop ENUM types
    op.execute("DROP TYPE llm_reasoning_widget_enum")
    op.execute("DROP TYPE llm_model_kind_enum")
