"""Add 'edge' to llm_provider_enum and drop the legacy voice_tts_mode system setting.

Schema:
- Adds 'edge' value to ``llm_provider_enum`` (Edge TTS, the free Microsoft
  Azure voice library used as the default ``standard`` mode). Implemented
  via the standard rename/create/alter-column/drop dance because
  PostgreSQL forbids ``ALTER TYPE ... ADD VALUE`` inside a transaction
  block. A dynamic pg_attribute lookup migrates every column that depends
  on the ENUM (currently ``llm_models.provider`` and
  ``image_generation_pricing.provider``).

Data:
- Removes the row ``system_settings.voice_tts_mode`` (key='voice_tts_mode')
  if present. The single source of truth for TTS configuration is now the
  ``llm_config_overrides.voice_tts`` row plus its ``provider_config``
  JSONB (cf. ADR-081 / refonte TTS).

Downgrade:
- Reverts the enum to its 8-value state. Refuses if any ``llm_models``
  row uses ``provider='edge'`` (PostgreSQL cannot drop an in-use enum
  value safely; admins must remove those rows manually first).
- The ``voice_tts_mode`` system setting is NOT restored — its data was
  always ephemeral admin preference, regenerable via the new admin UI.

Revision ID: edge_provider_001
Revises: stt_aggregates_user_pref_001
Create Date: 2026-05-07
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "edge_provider_001"
down_revision: str | None = "stt_aggregates_user_pref_001"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


PROVIDER_VALUES_BEFORE: tuple[str, ...] = (
    "openai",
    "anthropic",
    "deepseek",
    "perplexity",
    "ollama",
    "gemini",
    "qwen",
    "elevenlabs",
)
PROVIDER_VALUES_AFTER: tuple[str, ...] = (*PROVIDER_VALUES_BEFORE, "edge")


def _quoted_csv(values: tuple[str, ...]) -> str:
    return ", ".join(f"'{v}'" for v in values)


_MIGRATE_PROVIDER_COLUMNS_SQL = """
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
        WHERE ty.typname = '{old_type}'
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


def upgrade() -> None:
    # === 1. Recreate llm_provider_enum to add 'edge' ===
    op.execute("ALTER TYPE llm_provider_enum RENAME TO llm_provider_enum_old")
    op.execute(
        f"CREATE TYPE llm_provider_enum AS ENUM ({_quoted_csv(PROVIDER_VALUES_AFTER)})"
    )
    op.execute(_MIGRATE_PROVIDER_COLUMNS_SQL.format(old_type="llm_provider_enum_old"))
    op.execute("DROP TYPE llm_provider_enum_old")

    # === 2. Drop the legacy system_settings.voice_tts_mode row ===
    # The TTS mode (standard|hd) is replaced by the LLM type
    # 'voice_tts' configured through Configuration LLM (provider/model/
    # provider_config JSONB). The row itself is harmless to keep, but we
    # remove it so the admin UI doesn't surface a ghost setting.
    op.execute("DELETE FROM system_settings WHERE key = 'voice_tts_mode'")


def downgrade() -> None:
    bind = op.get_bind()
    edge_count = bind.execute(
        sa.text("SELECT COUNT(*) FROM llm_models WHERE provider = 'edge'")
    ).scalar()
    if edge_count and edge_count > 0:
        raise RuntimeError(
            f"Cannot downgrade: {edge_count} llm_models row(s) still use "
            "provider='edge'. Remove them (and dependent llm_model_pricing / "
            "llm_config_overrides rows) before running this downgrade."
        )

    op.execute("ALTER TYPE llm_provider_enum RENAME TO llm_provider_enum_new")
    op.execute(
        f"CREATE TYPE llm_provider_enum AS ENUM ({_quoted_csv(PROVIDER_VALUES_BEFORE)})"
    )
    op.execute(_MIGRATE_PROVIDER_COLUMNS_SQL.format(old_type="llm_provider_enum_new"))
    op.execute("DROP TYPE llm_provider_enum_new")
    # voice_tts_mode is intentionally not restored.
