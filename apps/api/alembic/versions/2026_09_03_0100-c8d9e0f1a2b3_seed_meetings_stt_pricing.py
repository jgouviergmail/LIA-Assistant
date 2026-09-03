"""Seed the tariffs of the two OpenAI speech engines the meetings pipeline calls (ADR-258).

Revision ID: c8d9e0f1a2b3
Revises: b7c8d9e0f1a2
Create Date: 2026-09-03 01:00:00.000000

Production never replays the reference SQL seed bundle (``APPLY_SEEDS`` is a
fresh-install switch), so an instance upgraded to the meetings release would
have transcribed with ``gpt-4o-transcribe-diarize`` and billed it nothing: the
pricing cache answers (0, 0) for a model it does not know, the meeting stores a
``null`` cost, and the platform cannot re-bill the audio. The catalogue rows and
their tariffs therefore travel by migration, the way ``seed_openai_pricing`` did.

Two rules, both about not inventing business data (ADR-228):

* a catalogue row is inserted only when the model is unknown — ``ON CONFLICT
  (model_name) DO NOTHING``;
* a tariff is inserted only when the model has NO active tariff. An
  administered price (set through the admin UI or the workbook) is never
  overridden, and the partial unique index ``uq_llm_model_pricing_active`` can
  never be violated. When OUR row already exists retired (a downgrade retires,
  it never deletes), the conflict re-activates it — ``DO UPDATE``, never
  ``DO NOTHING``, or a downgrade/upgrade cycle would leave the model with no
  active tariff, billed zero in silence (the defect class ADR-228 named).

The values mirror ``infrastructure/database/seeds/llm_pricing_seed.sql`` row for
row (same ``effective_from``, so the bundle's ``ON CONFLICT (model_id,
effective_from) DO UPDATE`` lands on the same row on a fresh install) — a guard
test holds the two sources equal.
"""

from __future__ import annotations

from collections.abc import Sequence

from alembic import op
from sqlalchemy import text

# revision identifiers, used by Alembic.
revision: str = "c8d9e0f1a2b3"
down_revision: str | None = "b7c8d9e0f1a2"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

#: (model_name, USD per audio minute) — the seed bundle's figures, verbatim.
STT_TARIFFS: tuple[tuple[str, float], ...] = (
    ("gpt-4o-transcribe-diarize", 0.006),
    ("gpt-4o-mini-transcribe", 0.003),
)
#: Same instant as the seed bundle, so both sources describe ONE tariff row.
EFFECTIVE_FROM = "2026-09-02T12:00:00+00:00"
PRICING_UNIT = "per_audio_minute"

_INSERT_MODEL = text("""
    INSERT INTO llm_models (
        provider, model_name, max_input_tokens, max_output_tokens,
        supports_tools, supports_structured_output, supports_strict_mode,
        supports_streaming, supports_vision, is_reasoning_model,
        supports_temperature, supports_top_p, supports_frequency_penalty,
        supports_presence_penalty, kind, reasoning_enum_values,
        reasoning_doc_i18n_key, is_active
    ) VALUES (
        'openai', :model_name, 1, 1,
        false, false, false,
        false, false, false,
        false, false, false,
        false, 'audio', NULL,
        NULL, true
    )
    ON CONFLICT (model_name) DO NOTHING
    """)

_INSERT_TARIFF = text("""
    INSERT INTO llm_model_pricing (
        id, model_id, input_unit_price, cached_input_unit_price, output_unit_price,
        pricing_unit, effective_from, is_active, created_at, updated_at
    )
    SELECT gen_random_uuid(), m.id, :input_price, NULL, 0,
           CAST(:unit AS pricing_unit_enum), CAST(:effective_from AS timestamptz),
           true, NOW(), NOW()
      FROM llm_models m
     WHERE m.model_name = :model_name
       AND NOT EXISTS (
           SELECT 1 FROM llm_model_pricing p WHERE p.model_id = m.id AND p.is_active
       )
    ON CONFLICT (model_id, effective_from) DO UPDATE
       SET is_active = true, updated_at = NOW()
    """)

_RETIRE_TARIFF = text("""
    UPDATE llm_model_pricing p
       SET is_active = false, updated_at = NOW()
      FROM llm_models m
     WHERE m.id = p.model_id
       AND m.model_name = :model_name
       AND p.effective_from = CAST(:effective_from AS timestamptz)
    """)


def upgrade() -> None:
    """Add the two speech models and their tariff where nothing administered exists."""
    bind = op.get_bind()
    for model_name, input_price in STT_TARIFFS:
        bind.execute(_INSERT_MODEL, {"model_name": model_name})
        bind.execute(
            _INSERT_TARIFF,
            {
                "model_name": model_name,
                "input_price": input_price,
                "unit": PRICING_UNIT,
                "effective_from": EFFECTIVE_FROM,
            },
        )


def downgrade() -> None:
    """Retire the tariff rows this migration may have added; the catalogue rows stay.

    Retiring keeps history (the doctrine of the seed bundle) and a catalogue row
    without an active tariff is exactly the state the upgrade found. The rows are
    identified by their ``effective_from``, so an administered tariff (any other
    instant) is left untouched.
    """
    bind = op.get_bind()
    for model_name, _ in STT_TARIFFS:
        bind.execute(_RETIRE_TARIFF, {"model_name": model_name, "effective_from": EFFECTIVE_FROM})
