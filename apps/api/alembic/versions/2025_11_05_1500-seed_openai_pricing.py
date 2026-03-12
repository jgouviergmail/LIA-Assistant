"""Seed OpenAI LLM pricing (GPT-5.x, GPT-4.1, GPT-4o, O-series, Image, Audio, etc.)

Revision ID: seed_openai_pricing
Revises: multi_provider_pricing_001
Create Date: 2025-11-05 15:00:00.000000

Adds comprehensive pricing for OpenAI models:
- GPT-5 Series: gpt-5, gpt-5.1, gpt-5.2, gpt-5.3, gpt-5-mini, gpt-5-nano, codex, pro
- GPT-4.1 Series: gpt-4.1, gpt-4.1-mini, gpt-4.1-nano
- GPT-4o Series: gpt-4o, gpt-4o-mini, search/audio/realtime previews
- GPT Realtime Series: gpt-realtime, gpt-realtime-1.5, gpt-realtime-mini
- GPT Audio Series: gpt-audio, gpt-audio-1.5, gpt-audio-mini
- GPT Image Series: gpt-image-1, gpt-image-1.5, gpt-image-1-mini, chatgpt-image-latest
- O-Series (Reasoning): o1, o1-pro, o1-mini
- O3-Series: o3, o3-pro, o3-mini, o3-deep-research
- O4-Series: o4-mini, o4-mini-deep-research
- Specialized: codex-mini-latest, computer-use-preview

Also seeds currency exchange rates (USD to EUR).
"""

from collections.abc import Sequence
from datetime import UTC, datetime

from sqlalchemy import text

from alembic import op

# revision identifiers, used by Alembic.
revision: str = 'seed_openai_pricing'
down_revision: str | None = 'multi_provider_pricing_001'
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Seed OpenAI LLM pricing and currency rates."""

    now = datetime.now(UTC)

    # ========================================================================
    # OPENAI PRICING - All Models
    # Source: https://platform.openai.com/docs/pricing
    # ========================================================================

    openai_pricing = [
        # GPT-5 Series
        {'model_name': 'gpt-5', 'input': 1.25, 'cached': 0.125, 'output': 10.00},
        {'model_name': 'gpt-5-mini', 'input': 0.25, 'cached': 0.025, 'output': 2.00},
        {'model_name': 'gpt-5-nano', 'input': 0.05, 'cached': 0.005, 'output': 0.40},
        {'model_name': 'gpt-5-chat-latest', 'input': 1.25, 'cached': 0.125, 'output': 10.00},
        {'model_name': 'gpt-5-codex', 'input': 1.25, 'cached': 0.125, 'output': 10.00},
        {'model_name': 'gpt-5-pro', 'input': 15.00, 'cached': None, 'output': 120.00},
        {'model_name': 'gpt-5-search-api', 'input': 1.25, 'cached': 0.125, 'output': 10.00},

        # GPT-5.1 Series
        {'model_name': 'gpt-5.1', 'input': 1.25, 'cached': 0.125, 'output': 10.00},
        {'model_name': 'gpt-5.1-chat-latest', 'input': 1.25, 'cached': 0.125, 'output': 10.00},
        {'model_name': 'gpt-5.1-codex', 'input': 1.25, 'cached': 0.125, 'output': 10.00},
        {'model_name': 'gpt-5.1-codex-max', 'input': 1.25, 'cached': 0.125, 'output': 10.00},
        {'model_name': 'gpt-5.1-codex-mini', 'input': 0.25, 'cached': 0.025, 'output': 2.00},

        # GPT-5.2 Series
        {'model_name': 'gpt-5.2', 'input': 1.75, 'cached': 0.175, 'output': 14.00},
        {'model_name': 'gpt-5.2-chat-latest', 'input': 1.75, 'cached': 0.175, 'output': 14.00},
        {'model_name': 'gpt-5.2-codex', 'input': 1.75, 'cached': 0.175, 'output': 14.00},
        {'model_name': 'gpt-5.2-pro', 'input': 21.00, 'cached': None, 'output': 168.00},

        # GPT-5.3 Series
        {'model_name': 'gpt-5.3-chat-latest', 'input': 1.75, 'cached': 0.175, 'output': 14.00},
        {'model_name': 'gpt-5.3-codex', 'input': 1.75, 'cached': 0.175, 'output': 14.00},

        # GPT-4.1 Series
        {'model_name': 'gpt-4.1', 'input': 2.00, 'cached': 0.50, 'output': 8.00},
        {'model_name': 'gpt-4.1-mini', 'input': 0.40, 'cached': 0.10, 'output': 1.60},
        {'model_name': 'gpt-4.1-nano', 'input': 0.10, 'cached': 0.025, 'output': 0.40},
        {'model_name': 'gpt-4.1-mini-mini', 'input': 0.15, 'cached': 0.075, 'output': 0.60},
        {'model_name': 'gpt-4.1-mini-search-preview', 'input': 2.50, 'cached': None, 'output': 10.00},
        {'model_name': 'gpt-4.1-mini-mini-search-preview', 'input': 0.15, 'cached': None, 'output': 0.60},

        # GPT-4o Series
        {'model_name': 'gpt-4o', 'input': 2.50, 'cached': 1.25, 'output': 10.00},
        {'model_name': 'gpt-4o-2024-05-13', 'input': 5.00, 'cached': None, 'output': 15.00},
        {'model_name': 'gpt-4o-mini', 'input': 0.15, 'cached': 0.075, 'output': 0.60},
        {'model_name': 'gpt-4o-search-preview', 'input': 2.50, 'cached': None, 'output': 10.00},
        {'model_name': 'gpt-4o-mini-search-preview', 'input': 0.15, 'cached': None, 'output': 0.60},
        {'model_name': 'gpt-4o-audio-preview', 'input': 2.50, 'cached': None, 'output': 10.00},
        {'model_name': 'gpt-4o-mini-audio-preview', 'input': 0.15, 'cached': None, 'output': 0.60},
        {'model_name': 'gpt-4o-realtime-preview', 'input': 5.00, 'cached': 2.50, 'output': 20.00},
        {'model_name': 'gpt-4o-mini-realtime-preview', 'input': 0.60, 'cached': 0.30, 'output': 2.40},

        # GPT Realtime Series
        {'model_name': 'gpt-realtime', 'input': 4.00, 'cached': 0.40, 'output': 16.00},
        {'model_name': 'gpt-realtime-1.5', 'input': 4.00, 'cached': 0.40, 'output': 16.00},
        {'model_name': 'gpt-realtime-mini', 'input': 0.60, 'cached': 0.06, 'output': 2.40},
        {'model_name': 'gpt-4.1-mini-realtime-preview', 'input': 5.00, 'cached': 2.50, 'output': 20.00},
        {'model_name': 'gpt-4.1-mini-mini-realtime-preview', 'input': 0.60, 'cached': 0.30, 'output': 2.40},

        # GPT Audio Series
        {'model_name': 'gpt-audio', 'input': 2.50, 'cached': None, 'output': 10.00},
        {'model_name': 'gpt-audio-1.5', 'input': 2.50, 'cached': None, 'output': 10.00},
        {'model_name': 'gpt-audio-mini', 'input': 0.60, 'cached': None, 'output': 2.40},
        {'model_name': 'gpt-4.1-mini-audio-preview', 'input': 2.50, 'cached': None, 'output': 10.00},
        {'model_name': 'gpt-4.1-mini-mini-audio-preview', 'input': 0.15, 'cached': None, 'output': 0.60},

        # GPT Image Series
        {'model_name': 'gpt-image-1', 'input': 5.00, 'cached': 1.25, 'output': 0.00},
        {'model_name': 'gpt-image-1.5', 'input': 5.00, 'cached': 1.25, 'output': 10.00},
        {'model_name': 'gpt-image-1-mini', 'input': 2.00, 'cached': 0.20, 'output': 0.00},
        {'model_name': 'chatgpt-image-latest', 'input': 5.00, 'cached': 1.25, 'output': 10.00},

        # O-Series (Reasoning Models)
        {'model_name': 'o1', 'input': 15.00, 'cached': 7.50, 'output': 60.00},
        {'model_name': 'o1-pro', 'input': 150.00, 'cached': None, 'output': 600.00},
        {'model_name': 'o1-mini', 'input': 1.10, 'cached': 0.55, 'output': 4.40},

        # O3-Series
        {'model_name': 'o3', 'input': 2.00, 'cached': 0.50, 'output': 8.00},
        {'model_name': 'o3-pro', 'input': 20.00, 'cached': None, 'output': 80.00},
        {'model_name': 'o3-mini', 'input': 1.10, 'cached': 0.55, 'output': 4.40},
        {'model_name': 'o3-deep-research', 'input': 10.00, 'cached': 2.50, 'output': 40.00},

        # O4-Series
        {'model_name': 'o4-mini', 'input': 1.10, 'cached': 0.275, 'output': 4.40},
        {'model_name': 'o4-mini-deep-research', 'input': 2.00, 'cached': 0.50, 'output': 8.00},

        # Specialized Models
        {'model_name': 'codex-mini-latest', 'input': 1.50, 'cached': 0.375, 'output': 6.00},
        {'model_name': 'computer-use-preview', 'input': 3.00, 'cached': None, 'output': 12.00},
    ]

    # Insert pricing entries with conflict handling (idempotent)
    conn = op.get_bind()
    for pricing in openai_pricing:
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

    # ========================================================================
    # CURRENCY EXCHANGE RATES
    # ========================================================================

    currency_rates = [
        # USD to EUR (1 USD = 0.95 EUR)
        {'from_cur': 'USD', 'to_cur': 'EUR', 'rate': 0.95},
        # EUR to USD (inverse rate for bidirectional conversion)
        {'from_cur': 'EUR', 'to_cur': 'USD', 'rate': 1.052632},
        # USD to USD (identity for default case)
        {'from_cur': 'USD', 'to_cur': 'USD', 'rate': 1.0},
    ]

    for rate_entry in currency_rates:
        conn.execute(
            text("""
                INSERT INTO currency_exchange_rates (
                    id,
                    from_currency,
                    to_currency,
                    rate,
                    effective_from,
                    is_active,
                    created_at,
                    updated_at
                ) VALUES (
                    gen_random_uuid(),
                    :from_cur,
                    :to_cur,
                    :rate,
                    :effective_from,
                    true,
                    :created_at,
                    :updated_at
                )
                ON CONFLICT (from_currency, to_currency, effective_from) DO NOTHING
            """),
            {
                'from_cur': rate_entry['from_cur'],
                'to_cur': rate_entry['to_cur'],
                'rate': rate_entry['rate'],
                'effective_from': now,
                'created_at': now,
                'updated_at': now,
            }
        )


def downgrade() -> None:
    """Remove OpenAI pricing seed data."""

    # List of all OpenAI model names to remove
    model_names = [
        # GPT-5 Series
        'gpt-5', 'gpt-5-mini', 'gpt-5-nano', 'gpt-5-chat-latest', 'gpt-5-codex',
        'gpt-5-pro', 'gpt-5-search-api',
        # GPT-5.1 Series
        'gpt-5.1', 'gpt-5.1-chat-latest', 'gpt-5.1-codex', 'gpt-5.1-codex-max',
        'gpt-5.1-codex-mini',
        # GPT-5.2 Series
        'gpt-5.2', 'gpt-5.2-chat-latest', 'gpt-5.2-codex', 'gpt-5.2-pro',
        # GPT-5.3 Series
        'gpt-5.3-chat-latest', 'gpt-5.3-codex',
        # GPT-4.1 Series
        'gpt-4.1', 'gpt-4.1-mini', 'gpt-4.1-nano',
        'gpt-4.1-mini-mini', 'gpt-4.1-mini-search-preview',
        'gpt-4.1-mini-mini-search-preview',
        # GPT-4o Series
        'gpt-4o', 'gpt-4o-2024-05-13', 'gpt-4o-mini',
        'gpt-4o-search-preview', 'gpt-4o-mini-search-preview',
        'gpt-4o-audio-preview', 'gpt-4o-mini-audio-preview',
        'gpt-4o-realtime-preview', 'gpt-4o-mini-realtime-preview',
        # GPT Realtime Series
        'gpt-realtime', 'gpt-realtime-1.5', 'gpt-realtime-mini',
        'gpt-4.1-mini-realtime-preview', 'gpt-4.1-mini-mini-realtime-preview',
        # GPT Audio Series
        'gpt-audio', 'gpt-audio-1.5', 'gpt-audio-mini',
        'gpt-4.1-mini-audio-preview', 'gpt-4.1-mini-mini-audio-preview',
        # GPT Image Series
        'gpt-image-1', 'gpt-image-1.5', 'gpt-image-1-mini', 'chatgpt-image-latest',
        # O-Series
        'o1', 'o1-pro', 'o1-mini',
        # O3-Series
        'o3', 'o3-pro', 'o3-mini', 'o3-deep-research',
        # O4-Series
        'o4-mini', 'o4-mini-deep-research',
        # Specialized
        'codex-mini-latest', 'computer-use-preview',
    ]

    conn = op.get_bind()
    for model_name in model_names:
        conn.execute(
            text("DELETE FROM llm_model_pricing WHERE model_name = :model_name"),
            {'model_name': model_name}
        )

    # Remove currency rates
    conn.execute(text("DELETE FROM currency_exchange_rates WHERE from_currency IN ('USD', 'EUR')"))
