"""Pinned Jev decision model and tariff; existing operator rows take precedence.

Revision ID: b138c047a5d2
Revises: 8bd197e03fa6

TypeSafe models/API documentation, checked 2026-09-28:
https://docs.typesafe.ai/models and https://docs.typesafe.ai/api
USD 0.042 per million input tokens, free outputs. Native Choice accepts no
sampling, reasoning, streaming, or chat structured-output parameters. The one
output token is a catalogue placeholder; no output budget is sent to TypeSafe.
The input bound is conservatively 32,000 for the single-question integration.
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "b138c047a5d2"
down_revision: str | None = "8bd197e03fa6"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

INSERT_MODEL = sa.text("""
    INSERT INTO llm_models (
        id, created_at, updated_at, provider, model_name, max_input_tokens, max_output_tokens,
        supports_tools, supports_structured_output, supports_strict_mode, supports_streaming,
        supports_vision, is_reasoning_model, supports_temperature, supports_top_p,
        supports_frequency_penalty, supports_presence_penalty, kind, is_active, capability_provenance
    ) VALUES (
        'b3aceb9c-bd2a-4cb6-a0ab-cd9108e4e128', NOW(), NOW(), 'typesafe', 'jev-1.13.0', 32000, 1,
        false, false, false, false, false, false, false, false, false, false,
        'decision', true, 'verified'
    ) ON CONFLICT (model_name) DO NOTHING
""")

INSERT_TARIFF = sa.text("""
    INSERT INTO llm_model_pricing (
        id, model_id, input_unit_price, cached_input_unit_price, output_unit_price,
        pricing_unit, effective_from, is_active, created_at, updated_at
    )
    SELECT 'cf5c9b68-65b3-4403-a2da-d044fd3bca23', m.id, 0.042, NULL, 0, 'per_1m_tokens',
           '2026-09-28T00:00:00+00:00', true, NOW(), NOW()
      FROM llm_models m WHERE m.model_name = 'jev-1.13.0' AND m.provider = 'typesafe'
       AND NOT EXISTS (SELECT 1 FROM llm_model_pricing p WHERE p.model_id = m.id AND p.is_active)
    ON CONFLICT (model_id, effective_from) DO NOTHING
""")


def upgrade() -> None:
    op.execute(INSERT_MODEL)
    op.execute(INSERT_TARIFF)


def downgrade() -> None:
    # Never erase an operator tariff, a selected model, or recorded native spend.
    protected = op.get_bind().scalar(sa.text("""
        SELECT EXISTS (SELECT 1 FROM llm_config_overrides WHERE provider = 'typesafe' OR model = 'jev-1.13.0')
            OR EXISTS (SELECT 1 FROM system_settings WHERE key IN ('JEV_ENABLED', 'JEV_MEETING_TEMPLATE_ENABLED'))
            OR EXISTS (SELECT 1 FROM meetings WHERE template_selection_usage IS NOT NULL)
            OR EXISTS (SELECT 1 FROM token_usage_logs WHERE provider = 'typesafe' OR model_name = 'jev-1.13.0')
            OR EXISTS (SELECT 1 FROM llm_models WHERE
                (id = 'b3aceb9c-bd2a-4cb6-a0ab-cd9108e4e128' OR kind = 'decision' OR provider = 'typesafe') AND
                (id <> 'b3aceb9c-bd2a-4cb6-a0ab-cd9108e4e128' OR updated_at <> created_at
                 OR provider <> 'typesafe' OR model_name <> 'jev-1.13.0' OR kind <> 'decision'
                 OR max_input_tokens <> 32000 OR max_output_tokens <> 1 OR NOT is_active
                 OR capability_provenance <> 'verified'
                 OR supports_tools OR supports_structured_output OR supports_strict_mode
                 OR supports_streaming OR supports_vision OR is_reasoning_model
                 OR supports_temperature OR supports_top_p OR supports_frequency_penalty OR supports_presence_penalty))
            OR EXISTS (
                SELECT 1 FROM llm_model_pricing p JOIN llm_models m ON m.id = p.model_id
                 WHERE m.model_name = 'jev-1.13.0' AND
                   (p.id <> 'cf5c9b68-65b3-4403-a2da-d044fd3bca23'
                    OR p.updated_at <> p.created_at OR NOT p.is_active
                    OR p.pricing_unit <> 'per_1m_tokens'
                    OR p.input_unit_price <> 0.042 OR p.output_unit_price <> 0
                    OR p.cached_input_unit_price IS NOT NULL OR p.time_slots IS NOT NULL
                    OR p.effective_from <> '2026-09-28T00:00:00+00:00')
            )
    """))
    if protected:
        raise RuntimeError(
            "Jev has configuration or usage; use its OFF switch to preserve operator data."
        )
    op.execute("DELETE FROM llm_model_pricing WHERE id = 'cf5c9b68-65b3-4403-a2da-d044fd3bca23'")
    op.execute("DELETE FROM llm_models WHERE id = 'b3aceb9c-bd2a-4cb6-a0ab-cd9108e4e128'")
