"""Add Jev 1.14 and Gemini 4 Argon without replacing administered rows.

Revision ID: 8e4c20f65b91
Revises: 3cb24a85d3f5

Official sources checked 2026-10-25:
https://docs.typesafe.ai/models
https://ai.google.dev/gemini-api/docs/models/gemini-4-argon
https://ai.google.dev/gemini-api/docs/latest-model
https://ai.google.dev/gemini-api/docs/pricing#gemini-4-argon

Jev remains a native decision model: 32K per question, no opt-in experimental
images/long context, and one output token as a catalogue placeholder only.
Argon uses the ordinary synchronous 64K output cap within its shared 1M window.
Its definitive Standard tariff (4 / 0.20 / 20 USD per million tokens) is applied
immediately at the owner's request; the promotion ends on 2026-11-30. Only
implicit caching is supported. No configured slot is retargeted.

Production does not replay the reference seed bundle, so upgraded instances
receive the same rows here. Existing catalogue rows and active tariffs win.
"""

from collections.abc import Sequence
from datetime import datetime

import sqlalchemy as sa
from alembic import op

revision: str = "8e4c20f65b91"
down_revision: str | None = "3cb24a85d3f5"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

EFFECTIVE_FROM = "2026-10-25T00:00:00+00:00"
EFFECTIVE_FROM_AT = datetime.fromisoformat(EFFECTIVE_FROM)

INSERT_MODELS = sa.text("""
    INSERT INTO llm_models (
        id, created_at, updated_at,
        provider, model_name, max_input_tokens, max_output_tokens,
        supports_tools, supports_structured_output, supports_strict_mode,
        supports_streaming, supports_vision, is_reasoning_model,
        supports_temperature, supports_top_p, supports_frequency_penalty,
        supports_presence_penalty, kind, reasoning_enum_values,
        reasoning_doc_i18n_key, is_active, capability_provenance
    ) VALUES
        (gen_random_uuid(), NOW(), NOW(),
         'typesafe', 'jev-1.14.0', 32000, 1,
         false, false, false, false, false, false, false, false, false, false,
         'decision', NULL, NULL, true, 'verified'),
        (gen_random_uuid(), NOW(), NOW(),
         'gemini', 'gemini-4-argon', 1048576, 65536,
         true, true, false, true, true, true, false, false, false, false,
         'chat', '["low", "medium", "high"]'::jsonb, NULL, true, 'verified')
    ON CONFLICT (model_name) DO NOTHING
""")

INSERT_TARIFFS = sa.text("""
    INSERT INTO llm_model_pricing (
        id, model_id, input_unit_price, cached_input_unit_price, output_unit_price,
        pricing_unit, effective_from, is_active, created_at, updated_at
    )
    SELECT gen_random_uuid(), m.id, v.input, v.cached, v.output,
           'per_1m_tokens', CAST(:effective_from AS timestamptz), true, NOW(), NOW()
      FROM (VALUES
          ('jev-1.14.0', 0.042000, NULL::numeric, 0.000000),
          ('gemini-4-argon', 4.000000, 0.200000, 20.000000)
      ) AS v(model_name, input, cached, output)
      JOIN llm_models m ON m.model_name = v.model_name
     WHERE NOT EXISTS (
         SELECT 1 FROM llm_model_pricing p WHERE p.model_id = m.id AND p.is_active
     )
    ON CONFLICT (model_id, effective_from) DO UPDATE
       SET is_active = true, updated_at = NOW()
""")


def upgrade() -> None:
    bind = op.get_bind()
    bind.execute(INSERT_MODELS)
    bind.execute(INSERT_TARIFFS, {"effective_from": EFFECTIVE_FROM_AT})


def downgrade() -> None:
    """Keep additive catalogue data, active prices and operator configuration.

    An upgrade can preserve an existing tariff at the same effective date;
    retiring by date would then retire a row this migration never inserted.
    Older application versions can read these rows without a schema change.
    """
