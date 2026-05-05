"""Backfill llm_models + linkage columns from frozen FALLBACK_PROFILES snapshot.

Step 2 of 3 toward making the LLM model catalogue DB-driven.

The model capability data below is a frozen snapshot of
``FALLBACK_PROFILES`` (apps/api/src/infrastructure/llm/model_profiles.py)
and ``IMAGE_GENERATION_MODELS`` (apps/api/src/domains/llm_config/constants.py)
as they exist at the time this migration is written. Once this release is
deployed those Python constants will be deleted; the data must therefore live
inside this migration so any future ``alembic upgrade head`` from a fresh DB
keeps working.

Operations (executed in a single transaction):
1. INSERT one row in ``llm_models`` per chat model in MODELS_DATA.
2. For every ``llm_model_pricing`` row that currently has ``model_id`` NULL,
   look up the matching ``llm_models.id`` by ``model_name`` and UPDATE.
   If a pricing row references an unknown ``model_name`` (legacy data),
   create a conservative ``llm_models`` row first with
   ``_guess_provider_from_model_name``.
3. For every ``image_generation_pricing`` row with ``provider`` NULL,
   look up the provider via IMAGE_PROVIDERS; default to ``openai`` for any
   remaining rows (legacy data — only OpenAI image models exist today).
4. Assert zero NULLs at the end (raises if backfill missed anything).

Reference: docs/superpowers/specs/2026-05-05-llm-models-db-source-of-truth-design.md

Revision ID: llm_models_002
Revises: llm_models_001
Create Date: 2026-05-05
"""

from collections.abc import Sequence
from typing import Any

import sqlalchemy as sa

from alembic import op

revision: str = "llm_models_002"
down_revision: str | None = "llm_models_001"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


# =============================================================================
# FROZEN DATA SNAPSHOT
# =============================================================================
# Each entry: (provider, model_name, max_input, max_output, sup_tools,
#              sup_struct, sup_strict, sup_streaming, sup_vision, is_reasoning)
# Bool order matches LLMModel column order.
MODELS_DATA: list[dict[str, Any]] = [
    # ---- OpenAI ----
    {
        "provider": "openai",
        "model_name": "gpt-4.1-mini",
        "max_input": 1047576,
        "max_output": 16384,
        "tools": True,
        "struct": True,
        "strict": True,
        "streaming": True,
        "vision": True,
        "reasoning": False,
    },
    {
        "provider": "openai",
        "model_name": "gpt-4.1-nano",
        "max_input": 1047576,
        "max_output": 16384,
        "tools": True,
        "struct": True,
        "strict": True,
        "streaming": True,
        "vision": True,
        "reasoning": False,
    },
    {
        "provider": "openai",
        "model_name": "gpt-4.1",
        "max_input": 1047576,
        "max_output": 32768,
        "tools": True,
        "struct": True,
        "strict": True,
        "streaming": True,
        "vision": True,
        "reasoning": False,
    },
    {
        "provider": "openai",
        "model_name": "gpt-5-mini",
        "max_input": 1047576,
        "max_output": 16384,
        "tools": True,
        "struct": True,
        "strict": True,
        "streaming": True,
        "vision": True,
        "reasoning": True,
    },
    {
        "provider": "openai",
        "model_name": "gpt-5-nano",
        "max_input": 1047576,
        "max_output": 16384,
        "tools": True,
        "struct": True,
        "strict": True,
        "streaming": True,
        "vision": True,
        "reasoning": True,
    },
    {
        "provider": "openai",
        "model_name": "gpt-5.4-mini",
        "max_input": 1047576,
        "max_output": 16384,
        "tools": True,
        "struct": True,
        "strict": True,
        "streaming": True,
        "vision": True,
        "reasoning": True,
    },
    {
        "provider": "openai",
        "model_name": "gpt-5.4",
        "max_input": 1047576,
        "max_output": 65536,
        "tools": True,
        "struct": True,
        "strict": True,
        "streaming": True,
        "vision": True,
        "reasoning": True,
    },
    {
        "provider": "openai",
        "model_name": "gpt-5.2",
        "max_input": 1047576,
        "max_output": 65536,
        "tools": True,
        "struct": True,
        "strict": True,
        "streaming": True,
        "vision": True,
        "reasoning": True,
    },
    {
        "provider": "openai",
        "model_name": "gpt-5.1",
        "max_input": 1047576,
        "max_output": 65536,
        "tools": True,
        "struct": True,
        "strict": True,
        "streaming": True,
        "vision": True,
        "reasoning": True,
    },
    {
        "provider": "openai",
        "model_name": "gpt-5",
        "max_input": 1047576,
        "max_output": 65536,
        "tools": True,
        "struct": True,
        "strict": True,
        "streaming": True,
        "vision": True,
        "reasoning": True,
    },
    {
        "provider": "openai",
        "model_name": "gpt-4o-mini",
        "max_input": 128000,
        "max_output": 16384,
        "tools": True,
        "struct": True,
        "strict": True,
        "streaming": True,
        "vision": True,
        "reasoning": False,
    },
    {
        "provider": "openai",
        "model_name": "gpt-4o",
        "max_input": 128000,
        "max_output": 16384,
        "tools": True,
        "struct": True,
        "strict": True,
        "streaming": True,
        "vision": True,
        "reasoning": False,
    },
    {
        "provider": "openai",
        "model_name": "o4-mini",
        "max_input": 200000,
        "max_output": 100000,
        "tools": True,
        "struct": True,
        "strict": True,
        "streaming": True,
        "vision": True,
        "reasoning": True,
    },
    {
        "provider": "openai",
        "model_name": "o3-mini",
        "max_input": 200000,
        "max_output": 100000,
        "tools": True,
        "struct": True,
        "strict": True,
        "streaming": True,
        "vision": True,
        "reasoning": True,
    },
    {
        "provider": "openai",
        "model_name": "o3",
        "max_input": 200000,
        "max_output": 100000,
        "tools": True,
        "struct": True,
        "strict": True,
        "streaming": True,
        "vision": True,
        "reasoning": True,
    },
    {
        "provider": "openai",
        "model_name": "o1-mini",
        "max_input": 128000,
        "max_output": 65536,
        "tools": True,
        "struct": True,
        "strict": True,
        "streaming": True,
        "vision": True,
        "reasoning": True,
    },
    {
        "provider": "openai",
        "model_name": "o1",
        "max_input": 200000,
        "max_output": 100000,
        "tools": True,
        "struct": True,
        "strict": True,
        "streaming": True,
        "vision": True,
        "reasoning": True,
    },
    # OpenAI embeddings — kept for completeness; pricing table tracks them too.
    {
        "provider": "openai",
        "model_name": "text-embedding-3-small",
        "max_input": 8192,
        "max_output": 0,
        "tools": False,
        "struct": False,
        "strict": False,
        "streaming": False,
        "vision": False,
        "reasoning": False,
    },
    {
        "provider": "openai",
        "model_name": "text-embedding-3-large",
        "max_input": 8192,
        "max_output": 0,
        "tools": False,
        "struct": False,
        "strict": False,
        "streaming": False,
        "vision": False,
        "reasoning": False,
    },
    {
        "provider": "openai",
        "model_name": "text-embedding-ada-002",
        "max_input": 8192,
        "max_output": 0,
        "tools": False,
        "struct": False,
        "strict": False,
        "streaming": False,
        "vision": False,
        "reasoning": False,
    },
    # ---- Anthropic ----
    {
        "provider": "anthropic",
        "model_name": "claude-opus-4-6",
        "max_input": 200000,
        "max_output": 32000,
        "tools": True,
        "struct": True,
        "strict": False,
        "streaming": True,
        "vision": True,
        "reasoning": False,
    },
    {
        "provider": "anthropic",
        "model_name": "claude-opus-4-5",
        "max_input": 200000,
        "max_output": 32000,
        "tools": True,
        "struct": True,
        "strict": False,
        "streaming": True,
        "vision": True,
        "reasoning": False,
    },
    {
        "provider": "anthropic",
        "model_name": "claude-opus-4",
        "max_input": 200000,
        "max_output": 32000,
        "tools": True,
        "struct": True,
        "strict": False,
        "streaming": True,
        "vision": True,
        "reasoning": False,
    },
    {
        "provider": "anthropic",
        "model_name": "claude-sonnet-4-6",
        "max_input": 200000,
        "max_output": 64000,
        "tools": True,
        "struct": True,
        "strict": False,
        "streaming": True,
        "vision": True,
        "reasoning": False,
    },
    {
        "provider": "anthropic",
        "model_name": "claude-sonnet-4-5",
        "max_input": 200000,
        "max_output": 64000,
        "tools": True,
        "struct": True,
        "strict": False,
        "streaming": True,
        "vision": True,
        "reasoning": False,
    },
    {
        "provider": "anthropic",
        "model_name": "claude-sonnet-4",
        "max_input": 200000,
        "max_output": 64000,
        "tools": True,
        "struct": True,
        "strict": False,
        "streaming": True,
        "vision": True,
        "reasoning": False,
    },
    {
        "provider": "anthropic",
        "model_name": "claude-haiku-4-5",
        "max_input": 200000,
        "max_output": 8192,
        "tools": True,
        "struct": True,
        "strict": False,
        "streaming": True,
        "vision": True,
        "reasoning": False,
    },
    {
        "provider": "anthropic",
        "model_name": "claude-3-5-sonnet-20241022",
        "max_input": 200000,
        "max_output": 8192,
        "tools": True,
        "struct": True,
        "strict": False,
        "streaming": True,
        "vision": True,
        "reasoning": False,
    },
    {
        "provider": "anthropic",
        "model_name": "claude-3-5-haiku-20241022",
        "max_input": 200000,
        "max_output": 8192,
        "tools": True,
        "struct": True,
        "strict": False,
        "streaming": True,
        "vision": True,
        "reasoning": False,
    },
    # ---- DeepSeek ----
    {
        "provider": "deepseek",
        "model_name": "deepseek-chat",
        "max_input": 128000,
        "max_output": 8192,
        "tools": True,
        "struct": True,
        "strict": False,
        "streaming": True,
        "vision": False,
        "reasoning": False,
    },
    {
        "provider": "deepseek",
        "model_name": "deepseek-reasoner",
        "max_input": 128000,
        "max_output": 64000,
        "tools": False,
        "struct": False,
        "strict": False,
        "streaming": True,
        "vision": False,
        "reasoning": True,
    },
    # ---- Gemini ----
    {
        "provider": "gemini",
        "model_name": "gemini-3.1-pro-preview",
        "max_input": 1000000,
        "max_output": 65536,
        "tools": True,
        "struct": True,
        "strict": False,
        "streaming": True,
        "vision": True,
        "reasoning": False,
    },
    {
        "provider": "gemini",
        "model_name": "gemini-3-pro-preview",
        "max_input": 1000000,
        "max_output": 65536,
        "tools": True,
        "struct": True,
        "strict": False,
        "streaming": True,
        "vision": True,
        "reasoning": False,
    },
    {
        "provider": "gemini",
        "model_name": "gemini-3-flash-preview",
        "max_input": 1000000,
        "max_output": 65536,
        "tools": True,
        "struct": True,
        "strict": False,
        "streaming": True,
        "vision": True,
        "reasoning": False,
    },
    {
        "provider": "gemini",
        "model_name": "gemini-2.5-pro",
        "max_input": 1000000,
        "max_output": 65536,
        "tools": True,
        "struct": True,
        "strict": False,
        "streaming": True,
        "vision": True,
        "reasoning": False,
    },
    {
        "provider": "gemini",
        "model_name": "gemini-2.5-flash-lite",
        "max_input": 1000000,
        "max_output": 65536,
        "tools": True,
        "struct": True,
        "strict": False,
        "streaming": True,
        "vision": True,
        "reasoning": False,
    },
    {
        "provider": "gemini",
        "model_name": "gemini-2.5-flash",
        "max_input": 1000000,
        "max_output": 65536,
        "tools": True,
        "struct": True,
        "strict": False,
        "streaming": True,
        "vision": True,
        "reasoning": False,
    },
    {
        "provider": "gemini",
        "model_name": "gemini-2.0-flash-lite",
        "max_input": 1000000,
        "max_output": 8192,
        "tools": True,
        "struct": True,
        "strict": False,
        "streaming": True,
        "vision": True,
        "reasoning": False,
    },
    {
        "provider": "gemini",
        "model_name": "gemini-2.0-flash",
        "max_input": 1000000,
        "max_output": 8192,
        "tools": True,
        "struct": True,
        "strict": False,
        "streaming": True,
        "vision": True,
        "reasoning": False,
    },
    # ---- Ollama (local) ----
    {
        "provider": "ollama",
        "model_name": "llama3.1",
        "max_input": 131072,
        "max_output": 4096,
        "tools": True,
        "struct": True,
        "strict": False,
        "streaming": True,
        "vision": False,
        "reasoning": False,
    },
    {
        "provider": "ollama",
        "model_name": "llama3.2",
        "max_input": 131072,
        "max_output": 4096,
        "tools": True,
        "struct": True,
        "strict": False,
        "streaming": True,
        "vision": True,
        "reasoning": False,
    },
    {
        "provider": "ollama",
        "model_name": "mistral",
        "max_input": 32768,
        "max_output": 4096,
        "tools": True,
        "struct": True,
        "strict": False,
        "streaming": True,
        "vision": False,
        "reasoning": False,
    },
    {
        "provider": "ollama",
        "model_name": "qwen2.5",
        "max_input": 131072,
        "max_output": 8192,
        "tools": True,
        "struct": True,
        "strict": False,
        "streaming": True,
        "vision": False,
        "reasoning": False,
    },
    # ---- Qwen (DashScope OpenAI-compatible) ----
    {
        "provider": "qwen",
        "model_name": "qwen3-max",
        "max_input": 262144,
        "max_output": 65536,
        "tools": False,
        "struct": True,
        "strict": False,
        "streaming": True,
        "vision": False,
        "reasoning": True,
    },
    {
        "provider": "qwen",
        "model_name": "qwen3.6-plus",
        "max_input": 1000000,
        "max_output": 65536,
        "tools": True,
        "struct": True,
        "strict": False,
        "streaming": True,
        "vision": True,
        "reasoning": True,
    },
    {
        "provider": "qwen",
        "model_name": "qwen3.5-plus",
        "max_input": 1000000,
        "max_output": 65536,
        "tools": True,
        "struct": True,
        "strict": False,
        "streaming": True,
        "vision": True,
        "reasoning": True,
    },
    {
        "provider": "qwen",
        "model_name": "qwen3.5-flash",
        "max_input": 1000000,
        "max_output": 65536,
        "tools": True,
        "struct": True,
        "strict": False,
        "streaming": True,
        "vision": True,
        "reasoning": True,
    },
    # ---- Perplexity (search-augmented, limited capabilities) ----
    {
        "provider": "perplexity",
        "model_name": "llama-3.1-sonar-small-128k-online",
        "max_input": 127000,
        "max_output": 4096,
        "tools": False,
        "struct": False,
        "strict": False,
        "streaming": True,
        "vision": False,
        "reasoning": False,
    },
    {
        "provider": "perplexity",
        "model_name": "llama-3.1-sonar-large-128k-online",
        "max_input": 127000,
        "max_output": 4096,
        "tools": False,
        "struct": False,
        "strict": False,
        "streaming": True,
        "vision": False,
        "reasoning": False,
    },
]

# Image generation models — provider lookup for image_generation_pricing rows.
IMAGE_PROVIDERS: dict[str, str] = {
    "gpt-image-1.5": "openai",
    "gpt-image-1": "openai",
    "gpt-image-1-mini": "openai",
}


def _guess_provider_from_model_name(model_name: str) -> str:
    """Best-effort provider guess from a model_name prefix.

    Used only when a pricing row references a model_name not in MODELS_DATA
    (legacy data). Defaults to ``openai``.

    Known limitation: any future Perplexity model named ``llama-3.X-...``
    without ``-sonar`` in the prefix would be classified as ``ollama``. All
    current Perplexity models are listed in MODELS_DATA so this only matters
    for unanticipated legacy rows. Widen the perplexity prefix tuple if such
    models ever appear in production data.
    """
    n = model_name.lower()
    if n.startswith(("claude-", "anthropic")):
        return "anthropic"
    if n.startswith("deepseek"):
        return "deepseek"
    if n.startswith(("sonar", "perplexity", "llama-3.1-sonar")):
        return "perplexity"
    if n.startswith(("gemini", "models/gemini")):
        return "gemini"
    if n.startswith("qwen"):
        return "qwen"
    if n.startswith(("llama", "mistral", "phi", "mixtral")) or "/" in n:
        return "ollama"
    return "openai"


def upgrade() -> None:
    """Insert llm_models rows + backfill linkage columns."""
    bind = op.get_bind()

    # 1. Insert llm_models rows. ON CONFLICT DO NOTHING to be re-runnable
    #    even if the seed file or a previous attempt already populated them.
    insert_stmt = sa.text("""
        INSERT INTO llm_models (
            provider, model_name,
            max_input_tokens, max_output_tokens,
            supports_tools, supports_structured_output,
            supports_strict_mode, supports_streaming,
            supports_vision, is_reasoning_model,
            is_active
        ) VALUES (
            :provider, :model_name,
            :max_input, :max_output,
            :tools, :struct, :strict, :streaming,
            :vision, :reasoning,
            TRUE
        )
        ON CONFLICT (model_name) DO NOTHING
        """)
    for row in MODELS_DATA:
        bind.execute(insert_stmt, row)

    # 2. Backfill llm_model_pricing.model_id from model_name
    distinct_pricings = bind.execute(
        sa.text("SELECT DISTINCT model_name FROM llm_model_pricing WHERE model_id IS NULL")
    ).fetchall()

    for (model_name,) in distinct_pricings:
        # Ensure an llm_models row exists for this model_name
        existing = bind.execute(
            sa.text("SELECT id FROM llm_models WHERE model_name = :name"),
            {"name": model_name},
        ).fetchone()

        if existing is None:
            # Legacy pricing row references an unknown model — create a
            # conservative llm_models row so the FK can be satisfied.
            provider = _guess_provider_from_model_name(model_name)
            bind.execute(
                sa.text("""
                    INSERT INTO llm_models (
                        provider, model_name,
                        max_input_tokens, max_output_tokens,
                        supports_tools, supports_structured_output,
                        supports_strict_mode, supports_streaming,
                        supports_vision, is_reasoning_model,
                        is_active
                    ) VALUES (
                        :provider, :name,
                        8192, 4096,
                        TRUE, TRUE, FALSE, TRUE, FALSE, FALSE,
                        TRUE
                    )
                    """),
                {"provider": provider, "name": model_name},
            )

        bind.execute(
            sa.text("""
                UPDATE llm_model_pricing
                SET model_id = (SELECT id FROM llm_models WHERE model_name = :name)
                WHERE model_name = :name AND model_id IS NULL
                """),
            {"name": model_name},
        )

    # 3. Backfill image_generation_pricing.provider
    for image_model, provider in IMAGE_PROVIDERS.items():
        bind.execute(
            sa.text("""
                UPDATE image_generation_pricing
                SET provider = CAST(:provider AS llm_provider_enum)
                WHERE model = :model AND provider IS NULL
                """),
            {"provider": provider, "model": image_model},
        )

    # Any remaining unknown image rows → openai (only image provider today).
    # Use explicit ::llm_provider_enum cast for driver-independence (matches
    # the CAST(:provider AS llm_provider_enum) form used in the loop above).
    bind.execute(
        sa.text(
            "UPDATE image_generation_pricing "
            "SET provider = 'openai'::llm_provider_enum WHERE provider IS NULL"
        )
    )

    # 4. Final assertions — fail loud if backfill missed anything.
    null_pricings = bind.execute(
        sa.text("SELECT COUNT(*) FROM llm_model_pricing WHERE model_id IS NULL")
    ).scalar_one()
    if null_pricings:
        raise RuntimeError(f"Backfill failed: {null_pricings} llm_model_pricing rows still NULL")

    null_image = bind.execute(
        sa.text("SELECT COUNT(*) FROM image_generation_pricing WHERE provider IS NULL")
    ).scalar_one()
    if null_image:
        raise RuntimeError(
            f"Backfill failed: {null_image} image_generation_pricing rows still NULL"
        )


def downgrade() -> None:
    """Reset linkage columns to NULL and remove all llm_models rows."""
    op.execute("UPDATE llm_model_pricing SET model_id = NULL")
    op.execute("UPDATE image_generation_pricing SET provider = NULL")
    op.execute("DELETE FROM llm_models")
