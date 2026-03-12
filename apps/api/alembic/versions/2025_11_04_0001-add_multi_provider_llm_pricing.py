"""Add multi-provider LLM pricing (Anthropic, DeepSeek, Perplexity, Ollama)

Revision ID: multi_provider_pricing_001
Revises: f557be2223e8
Create Date: 2025-11-04 00:01:00.000000

Adds pricing for new LLM providers:
- Anthropic: Full Claude model line (Haiku, Sonnet, Opus) with cache pricing
- DeepSeek: deepseek-chat and deepseek-reasoner with cache pricing
- Perplexity: Sonar models (Sonar, Pro, Reasoning Pro, Deep Research)
- Ollama: Free (local deployment)

Note: Anthropic has tiered pricing (≤200K vs >200K tokens).
For simplicity, we use base tier prices (≤200K tokens).
Models with both dash and dot naming variants are included for compatibility.
"""

from collections.abc import Sequence
from datetime import UTC, datetime

from sqlalchemy import text

from alembic import op

# revision identifiers, used by Alembic.
revision: str = 'multi_provider_pricing_001'
down_revision: str | None = 'f557be2223e8'  # Drop unused embeddings table
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Add pricing for Anthropic, DeepSeek, Perplexity, and Ollama models."""

    now = datetime.now(UTC)

    # ========================================================================
    # ANTHROPIC PRICING - Full Claude Model Line
    # ========================================================================
    # Source: https://docs.anthropic.com/en/docs/about-claude/models
    # Base tier (≤200K tokens). Cache = cache read price.
    # Both dash and dot naming variants for compatibility.

    anthropic_pricing = [
        # Claude Haiku 3
        {'model_name': 'claude-haiku-3', 'input': 0.25, 'cached': 0.03, 'output': 1.25},
        # Claude Haiku 3.5
        {'model_name': 'claude-haiku-3-5', 'input': 0.80, 'cached': 0.08, 'output': 4.00},
        {'model_name': 'claude-haiku-3.5', 'input': 0.80, 'cached': 0.08, 'output': 4.00},
        # Claude Haiku 4.5
        {'model_name': 'claude-haiku-4-5', 'input': 1.00, 'cached': 0.10, 'output': 5.00},
        {'model_name': 'claude-haiku-4.5', 'input': 1.00, 'cached': 0.10, 'output': 5.00},
        # Claude Sonnet 3.7
        {'model_name': 'claude-sonnet-3-7', 'input': 3.00, 'cached': 0.30, 'output': 15.00},
        {'model_name': 'claude-sonnet-3.7', 'input': 3.00, 'cached': 0.30, 'output': 15.00},
        # Claude Sonnet 4
        {'model_name': 'claude-sonnet-4', 'input': 3.00, 'cached': 0.30, 'output': 15.00},
        # Claude Sonnet 4.5
        {'model_name': 'claude-sonnet-4-5', 'input': 3.00, 'cached': 0.30, 'output': 15.00},
        {'model_name': 'claude-sonnet-4.5', 'input': 3.00, 'cached': 0.30, 'output': 15.00},
        # Claude Sonnet 4.6
        {'model_name': 'claude-sonnet-4-6', 'input': 3.00, 'cached': 0.30, 'output': 15.00},
        {'model_name': 'claude-sonnet-4.6', 'input': 3.00, 'cached': 0.30, 'output': 15.00},
        # Claude Opus 3
        {'model_name': 'claude-opus-3', 'input': 15.00, 'cached': 1.50, 'output': 75.00},
        # Claude Opus 4
        {'model_name': 'claude-opus-4', 'input': 15.00, 'cached': 1.50, 'output': 75.00},
        # Claude Opus 4.1
        {'model_name': 'claude-opus-4-1', 'input': 15.00, 'cached': 1.50, 'output': 75.00},
        {'model_name': 'claude-opus-4.1', 'input': 15.00, 'cached': 1.50, 'output': 75.00},
        # Claude Opus 4.5
        {'model_name': 'claude-opus-4-5', 'input': 5.00, 'cached': 0.50, 'output': 25.00},
        {'model_name': 'claude-opus-4.5', 'input': 5.00, 'cached': 0.50, 'output': 25.00},
        # Claude Opus 4.6
        {'model_name': 'claude-opus-4-6', 'input': 5.00, 'cached': 0.50, 'output': 25.00},
        {'model_name': 'claude-opus-4.6', 'input': 5.00, 'cached': 0.50, 'output': 25.00},
    ]

    # ========================================================================
    # DEEPSEEK PRICING
    # ========================================================================
    # deepseek-chat (V3): Input $0.28, Cache hit $0.028, Output $0.42

    deepseek_pricing = [
        {'model_name': 'deepseek-chat', 'input': 0.28, 'cached': 0.028, 'output': 0.42},
        {'model_name': 'deepseek-reasoner', 'input': 0.28, 'cached': 0.028, 'output': 0.42},
    ]

    # ========================================================================
    # PERPLEXITY PRICING
    # ========================================================================
    # Source: https://docs.perplexity.ai/docs/getting-started/pricing

    perplexity_pricing = [
        {'model_name': 'sonar', 'input': 1.00, 'cached': None, 'output': 1.00},
        {'model_name': 'sonar-pro', 'input': 3.00, 'cached': None, 'output': 15.00},
        {'model_name': 'sonar-reasoning-pro', 'input': 2.00, 'cached': None, 'output': 8.00},
        {'model_name': 'sonar-deep-research', 'input': 2.00, 'cached': None, 'output': 8.00},
    ]

    # ========================================================================
    # OLLAMA PRICING (Local deployment - Free)
    # ========================================================================

    ollama_pricing = [
        {'model_name': 'llama3.2', 'input': 0.00, 'cached': None, 'output': 0.00},
        {'model_name': 'mistral', 'input': 0.00, 'cached': None, 'output': 0.00},
        {'model_name': 'qwen2.5', 'input': 0.00, 'cached': None, 'output': 0.00},
    ]

    # Combine and insert all pricing entries
    all_pricing = anthropic_pricing + deepseek_pricing + perplexity_pricing + ollama_pricing

    conn = op.get_bind()
    for pricing in all_pricing:
        conn.execute(
            text("""
                INSERT INTO llm_model_pricing (
                    id, model_name,
                    input_price_per_1m_tokens, cached_input_price_per_1m_tokens,
                    output_price_per_1m_tokens, effective_from,
                    is_active, created_at, updated_at
                ) VALUES (
                    gen_random_uuid(), :model_name,
                    :input, :cached,
                    :output, :effective_from,
                    true, :created_at, :updated_at
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
    """Remove multi-provider pricing entries."""

    model_names = [
        # Anthropic
        'claude-haiku-3',
        'claude-haiku-3-5', 'claude-haiku-3.5',
        'claude-haiku-4-5', 'claude-haiku-4.5',
        'claude-sonnet-3-7', 'claude-sonnet-3.7',
        'claude-sonnet-4',
        'claude-sonnet-4-5', 'claude-sonnet-4.5',
        'claude-sonnet-4-6', 'claude-sonnet-4.6',
        'claude-opus-3',
        'claude-opus-4',
        'claude-opus-4-1', 'claude-opus-4.1',
        'claude-opus-4-5', 'claude-opus-4.5',
        'claude-opus-4-6', 'claude-opus-4.6',
        # DeepSeek
        'deepseek-chat', 'deepseek-reasoner',
        # Perplexity
        'sonar', 'sonar-pro', 'sonar-reasoning-pro', 'sonar-deep-research',
        # Ollama
        'llama3.2', 'mistral', 'qwen2.5',
    ]

    conn = op.get_bind()
    for model_name in model_names:
        conn.execute(
            text("DELETE FROM llm_model_pricing WHERE model_name = :model_name"),
            {'model_name': model_name}
        )
