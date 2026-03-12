"""Migrate LLM provider API keys from .env to database.

Revision ID: llm_config_002
Revises: llm_config_001
Create Date: 2026-03-08

One-time data migration: reads existing .env API keys and inserts them
as Fernet-encrypted rows into provider_api_keys table.
Idempotent: skips providers that already have a DB entry.
Skips empty or placeholder values (CHANGE_ME_*).

After this migration, .env API key fields are no longer read by the application.
Keys are managed exclusively via the Admin UI (Settings > Administration > LLM Configuration).
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "llm_config_002"
down_revision: str | None = "llm_config_001"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

# Provider key → .env variable name
_ENV_PROVIDERS: dict[str, str] = {
    "openai": "OPENAI_API_KEY",
    "anthropic": "ANTHROPIC_API_KEY",
    "deepseek": "DEEPSEEK_API_KEY",
    "perplexity": "PERPLEXITY_API_KEY",
    "gemini": "GOOGLE_GEMINI_API_KEY",
    "ollama": "OLLAMA_BASE_URL",
}


def upgrade() -> None:
    import os
    import uuid

    from src.core.security.utils import encrypt_data

    conn = op.get_bind()

    for provider, env_var in _ENV_PROVIDERS.items():
        value = os.environ.get(env_var, "")

        # Skip empty or placeholder values
        if not value or value.startswith("CHANGE_ME"):
            continue

        # Check if provider already has a DB entry (idempotent)
        exists = conn.execute(
            sa.text("SELECT 1 FROM provider_api_keys WHERE provider = :p"),
            {"p": provider},
        ).fetchone()
        if exists:
            continue

        # Insert encrypted key
        encrypted = encrypt_data(value)
        conn.execute(
            sa.text(
                "INSERT INTO provider_api_keys (id, provider, encrypted_key, created_at, updated_at) "
                "VALUES (:id, :provider, :encrypted_key, now(), now())"
            ),
            {
                "id": str(uuid.uuid4()),
                "provider": provider,
                "encrypted_key": encrypted,
            },
        )


def downgrade() -> None:
    # Cannot restore .env values from DB — no-op.
    # Keys remain in DB; .env fallback code was removed in the same release.
    pass
