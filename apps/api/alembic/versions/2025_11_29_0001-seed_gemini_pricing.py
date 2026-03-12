"""Seed Google Gemini LLM pricing

Revision ID: seed_gemini_pricing
Revises: add_connector_preferences
Create Date: 2025-11-29 00:01:00.000000

Adds comprehensive pricing for Google Gemini models:
- Gemini 3.1 Series (Preview): gemini-3.1-pro-preview, gemini-3.1-flash-lite-preview
- Gemini 3 Series (Preview): gemini-3-pro-preview, gemini-3-pro-image-preview, gemini-3-flash-preview
- Gemini 2.5 Pro Series: gemini-2.5-pro, gemini-2.5-pro-preview-tts
- Gemini 2.5 Flash Series: gemini-2.5-flash, gemini-2.5-flash-image, etc.
- Gemini 2.5 Flash-Lite Series: gemini-2.5-flash-lite
- Gemini 2.0 Flash Series: gemini-2.0-flash, gemini-2.0-flash-001, etc.
- Gemini 2.0 Flash-Lite Series: gemini-2.0-flash-lite
- Gemini Embedding: text-embedding-004, embedding-001, gemini-embedding-001

Source: https://ai.google.dev/gemini-api/docs/pricing
"""

from collections.abc import Sequence
from datetime import UTC, datetime

from sqlalchemy import text

from alembic import op

# revision identifiers, used by Alembic.
revision: str = 'seed_gemini_pricing'
down_revision: str | None = 'connector_preferences_001'
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Seed Google Gemini LLM pricing."""

    now = datetime.now(UTC)

    # ========================================================================
    # GOOGLE GEMINI PRICING - All Models (2025)
    # Source: https://ai.google.dev/gemini-api/docs/pricing
    # Prices in USD per 1 million tokens
    # ========================================================================

    gemini_pricing = [
        # Gemini 3.1 Series (Preview)
        {'model_name': 'gemini-3.1-pro-preview', 'input': 2.00, 'cached': 0.20, 'output': 12.00},
        {'model_name': 'gemini-3.1-flash-lite-preview', 'input': 0.25, 'cached': 0.025, 'output': 1.50},

        # Gemini 3 Series (Preview)
        {'model_name': 'gemini-3-pro-preview', 'input': 2.00, 'cached': 0.20, 'output': 12.00},
        {'model_name': 'gemini-3-pro-image-preview', 'input': 2.00, 'cached': 0.20, 'output': 12.00},
        {'model_name': 'gemini-3-flash-preview', 'input': 0.50, 'cached': 0.05, 'output': 3.00},

        # Gemini 2.5 Pro Series
        {'model_name': 'gemini-2.5-pro', 'input': 1.25, 'cached': 0.125, 'output': 10.00},
        {'model_name': 'gemini-2.5-pro-preview-tts', 'input': 1.25, 'cached': 0.125, 'output': 10.00},

        # Gemini 2.5 Flash Series
        {'model_name': 'gemini-2.5-flash', 'input': 0.30, 'cached': 0.03, 'output': 2.50},
        {'model_name': 'gemini-2.5-flash-preview-09-2025', 'input': 0.30, 'cached': 0.03, 'output': 2.50},
        {'model_name': 'gemini-2.5-flash-image', 'input': 0.30, 'cached': 0.03, 'output': 2.50},
        {'model_name': 'gemini-2.5-flash-image-preview', 'input': 0.30, 'cached': 0.03, 'output': 2.50},
        {'model_name': 'gemini-2.5-flash-native-audio-preview-09-2025', 'input': 1.00, 'cached': None, 'output': 2.50},
        {'model_name': 'gemini-2.5-flash-preview-tts', 'input': 0.30, 'cached': 0.03, 'output': 2.50},

        # Gemini 2.5 Flash-Lite Series
        {'model_name': 'gemini-2.5-flash-lite', 'input': 0.10, 'cached': 0.01, 'output': 0.40},
        {'model_name': 'gemini-2.5-flash-lite-preview-09-2025', 'input': 0.10, 'cached': 0.01, 'output': 0.40},

        # Gemini 2.0 Flash Series
        {'model_name': 'gemini-2.0-flash', 'input': 0.10, 'cached': 0.025, 'output': 0.40},
        {'model_name': 'gemini-2.0-flash-001', 'input': 0.10, 'cached': 0.025, 'output': 0.40},
        {'model_name': 'gemini-2.0-flash-exp', 'input': 0.10, 'cached': 0.025, 'output': 0.40},
        {'model_name': 'gemini-2.0-flash-preview-image-generation', 'input': 0.10, 'cached': 0.025, 'output': 0.40},
        {'model_name': 'gemini-2.0-flash-live-001', 'input': 0.35, 'cached': None, 'output': 1.50},

        # Gemini 2.0 Flash-Lite Series
        {'model_name': 'gemini-2.0-flash-lite', 'input': 0.075, 'cached': None, 'output': 0.30},
        {'model_name': 'gemini-2.0-flash-lite-001', 'input': 0.075, 'cached': None, 'output': 0.30},

        # Gemini Embedding
        {'model_name': 'gemini-embedding-001', 'input': 0.15, 'cached': None, 'output': 0.00},
        {'model_name': 'text-embedding-004', 'input': 0.15, 'cached': None, 'output': 0.00},
        {'model_name': 'embedding-001', 'input': 0.15, 'cached': None, 'output': 0.00},
    ]

    # Insert pricing entries with conflict handling (idempotent)
    conn = op.get_bind()
    for pricing in gemini_pricing:
        conn.execute(
            text("""
                INSERT INTO llm_model_pricing (
                    id,
                    model_name,
                    input_price_per_1m_tokens,
                    cached_input_price_per_1m_tokens,
                    output_price_per_1m_tokens,
                    effective_from,
                    is_active,
                    created_at,
                    updated_at
                ) VALUES (
                    gen_random_uuid(),
                    :model_name,
                    :input,
                    :cached,
                    :output,
                    :effective_from,
                    true,
                    :created_at,
                    :updated_at
                )
                ON CONFLICT (model_name, effective_from) DO NOTHING
            """),
            {
                'model_name': pricing['model_name'],
                'input': pricing['input'],
                'cached': pricing['cached'],
                'output': pricing['output'],
                'effective_from': now,
                'created_at': now,
                'updated_at': now,
            }
        )


def downgrade() -> None:
    """Remove Google Gemini pricing seed data."""

    # List of all Gemini model names to remove
    model_names = [
        # Gemini 3.1 Series
        'gemini-3.1-pro-preview', 'gemini-3.1-flash-lite-preview',
        # Gemini 3 Series
        'gemini-3-pro-preview', 'gemini-3-pro-image-preview', 'gemini-3-flash-preview',
        # Gemini 2.5 Pro Series
        'gemini-2.5-pro', 'gemini-2.5-pro-preview-tts',
        # Gemini 2.5 Flash Series
        'gemini-2.5-flash', 'gemini-2.5-flash-preview-09-2025',
        'gemini-2.5-flash-image', 'gemini-2.5-flash-image-preview',
        'gemini-2.5-flash-native-audio-preview-09-2025', 'gemini-2.5-flash-preview-tts',
        # Gemini 2.5 Flash-Lite Series
        'gemini-2.5-flash-lite', 'gemini-2.5-flash-lite-preview-09-2025',
        # Gemini 2.0 Flash Series
        'gemini-2.0-flash', 'gemini-2.0-flash-001', 'gemini-2.0-flash-exp',
        'gemini-2.0-flash-preview-image-generation', 'gemini-2.0-flash-live-001',
        # Gemini 2.0 Flash-Lite Series
        'gemini-2.0-flash-lite', 'gemini-2.0-flash-lite-001',
        # Gemini Embedding
        'gemini-embedding-001', 'text-embedding-004', 'embedding-001',
    ]

    conn = op.get_bind()
    for model_name in model_names:
        conn.execute(
            text("DELETE FROM llm_model_pricing WHERE model_name = :model_name"),
            {'model_name': model_name}
        )
