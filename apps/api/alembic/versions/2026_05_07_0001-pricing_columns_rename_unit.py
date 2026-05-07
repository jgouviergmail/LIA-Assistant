"""Rename llm_model_pricing price columns + add pricing_unit + add elevenlabs provider.

Schema changes:
- Renames 3 price columns on llm_model_pricing:
    input_price_per_1m_tokens         -> input_unit_price
    output_price_per_1m_tokens        -> output_unit_price
    cached_input_price_per_1m_tokens  -> cached_input_unit_price
  The semantics of these columns now depend on the new pricing_unit column.
- Adds llm_model_pricing.pricing_unit (NEW ENUM pricing_unit_enum):
    'per_1m_tokens'    -> default, current behaviour for chat/text models
    'per_audio_minute' -> billing per minute of audio (STT/TTS)
    'per_audio_hour'   -> billing per hour of audio (e.g. ElevenLabs Scribe)
- Adds 'elevenlabs' value to llm_provider_enum (via type recreation,
  ALTER TYPE ADD VALUE cannot run inside an Alembic transaction block).

Data:
- Existing rows are preserved (default 'per_1m_tokens'). No backfill needed.

Downgrade:
- Reverses column renames and drops pricing_unit + the new ENUM.
- Restores the original llm_provider_enum (drops 'elevenlabs'). PostgreSQL
  cannot remove an enum value with rows referencing it, so the downgrade
  asserts that no llm_models row has provider='elevenlabs'; if any exist
  they must be removed manually before running downgrade.

Revision ID: pricing_unit_rename_001
Revises: llm_sampling_flags_001
Create Date: 2026-05-07
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "pricing_unit_rename_001"
down_revision: str | None = "llm_sampling_flags_001"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


PROVIDER_VALUES_OLD: tuple[str, ...] = (
    "openai",
    "anthropic",
    "deepseek",
    "perplexity",
    "ollama",
    "gemini",
    "qwen",
)
PROVIDER_VALUES_NEW: tuple[str, ...] = (*PROVIDER_VALUES_OLD, "elevenlabs")
PRICING_UNIT_VALUES: tuple[str, ...] = (
    "per_1m_tokens",
    "per_audio_minute",
    "per_audio_hour",
)


def _quoted_csv(values: tuple[str, ...]) -> str:
    return ", ".join(f"'{v}'" for v in values)


def upgrade() -> None:
    # === 1. Recreate llm_provider_enum to add 'elevenlabs' ===
    # ALTER TYPE ... ADD VALUE cannot be executed inside a transaction block,
    # so we use the standard rename/create/alter-column/drop dance instead.
    # Multiple tables may declare a provider column on this ENUM (llm_models,
    # image_generation_pricing, …). We migrate every dependent column in one
    # pass via a pg_attribute lookup so the DROP TYPE at the end always
    # succeeds — no manual maintenance when a new table starts using the
    # type.
    op.execute("ALTER TYPE llm_provider_enum RENAME TO llm_provider_enum_old")
    op.execute(
        f"CREATE TYPE llm_provider_enum AS ENUM ({_quoted_csv(PROVIDER_VALUES_NEW)})"
    )
    op.execute(
        """
        DO $$
        DECLARE
            r RECORD;
        BEGIN
            FOR r IN
                SELECT n.nspname AS schema_name,
                       c.relname AS table_name,
                       a.attname AS column_name
                FROM pg_attribute a
                JOIN pg_class c ON a.attrelid = c.oid
                JOIN pg_namespace n ON c.relnamespace = n.oid
                JOIN pg_type ty ON a.atttypid = ty.oid
                WHERE ty.typname = 'llm_provider_enum_old'
                  AND c.relkind = 'r'
                  AND a.attnum > 0
                  AND NOT a.attisdropped
            LOOP
                EXECUTE format(
                    'ALTER TABLE %I.%I ALTER COLUMN %I TYPE llm_provider_enum '
                    'USING %I::text::llm_provider_enum',
                    r.schema_name, r.table_name, r.column_name, r.column_name
                );
            END LOOP;
        END $$;
        """
    )
    op.execute("DROP TYPE llm_provider_enum_old")

    # === 2. Create pricing_unit_enum ===
    op.execute(
        f"CREATE TYPE pricing_unit_enum AS ENUM ({_quoted_csv(PRICING_UNIT_VALUES)})"
    )

    # === 3. Rename price columns on llm_model_pricing ===
    op.alter_column(
        "llm_model_pricing",
        "input_price_per_1m_tokens",
        new_column_name="input_unit_price",
    )
    op.alter_column(
        "llm_model_pricing",
        "output_price_per_1m_tokens",
        new_column_name="output_unit_price",
    )
    op.alter_column(
        "llm_model_pricing",
        "cached_input_price_per_1m_tokens",
        new_column_name="cached_input_unit_price",
    )

    # === 4. Add pricing_unit column with default 'per_1m_tokens' ===
    op.add_column(
        "llm_model_pricing",
        sa.Column(
            "pricing_unit",
            sa.Enum(
                *PRICING_UNIT_VALUES,
                name="pricing_unit_enum",
                create_type=False,
            ),
            nullable=False,
            server_default="per_1m_tokens",
            comment=(
                "Billing unit semantics for input/output unit prices. "
                "'per_1m_tokens' (default) = price per 1 million tokens (LLM chat/text). "
                "'per_audio_minute' / 'per_audio_hour' = price per audio duration (STT/TTS)."
            ),
        ),
    )


def downgrade() -> None:
    # === Pre-flight: forbid downgrade if elevenlabs rows exist ===
    bind = op.get_bind()
    eleven_count = bind.execute(
        sa.text("SELECT COUNT(*) FROM llm_models WHERE provider = 'elevenlabs'")
    ).scalar()
    if eleven_count and eleven_count > 0:
        raise RuntimeError(
            f"Cannot downgrade: {eleven_count} llm_models row(s) still use "
            "provider='elevenlabs'. Remove them (and dependent llm_model_pricing / "
            "llm_config_overrides rows) before running this downgrade."
        )

    # === 4. Drop pricing_unit column ===
    op.drop_column("llm_model_pricing", "pricing_unit")

    # === 3. Reverse column renames ===
    op.alter_column(
        "llm_model_pricing",
        "cached_input_unit_price",
        new_column_name="cached_input_price_per_1m_tokens",
    )
    op.alter_column(
        "llm_model_pricing",
        "output_unit_price",
        new_column_name="output_price_per_1m_tokens",
    )
    op.alter_column(
        "llm_model_pricing",
        "input_unit_price",
        new_column_name="input_price_per_1m_tokens",
    )

    # === 2. Drop pricing_unit_enum ===
    op.execute("DROP TYPE pricing_unit_enum")

    # === 1. Restore original llm_provider_enum (without 'elevenlabs') ===
    # Same dynamic lookup as upgrade(): migrate every column that depends on
    # the renamed type, then drop the old shell.
    op.execute("ALTER TYPE llm_provider_enum RENAME TO llm_provider_enum_new")
    op.execute(
        f"CREATE TYPE llm_provider_enum AS ENUM ({_quoted_csv(PROVIDER_VALUES_OLD)})"
    )
    op.execute(
        """
        DO $$
        DECLARE
            r RECORD;
        BEGIN
            FOR r IN
                SELECT n.nspname AS schema_name,
                       c.relname AS table_name,
                       a.attname AS column_name
                FROM pg_attribute a
                JOIN pg_class c ON a.attrelid = c.oid
                JOIN pg_namespace n ON c.relnamespace = n.oid
                JOIN pg_type ty ON a.atttypid = ty.oid
                WHERE ty.typname = 'llm_provider_enum_new'
                  AND c.relkind = 'r'
                  AND a.attnum > 0
                  AND NOT a.attisdropped
            LOOP
                EXECUTE format(
                    'ALTER TABLE %I.%I ALTER COLUMN %I TYPE llm_provider_enum '
                    'USING %I::text::llm_provider_enum',
                    r.schema_name, r.table_name, r.column_name, r.column_name
                );
            END LOOP;
        END $$;
        """
    )
    op.execute("DROP TYPE llm_provider_enum_new")
