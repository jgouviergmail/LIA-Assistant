"""The ElevenLabs Agents live tariff (ADR-300 wave 4).

Revision ID: b7d1e3f5a9c2
Revises: f1a3c5e7b9d2
Create Date: 2026-09-19 21:00:00.000000

A live session on ElevenLabs runs on the person's OWN agent: its id is never
in the tariff table, so the provider prices every agent under ONE row,
``elevenlabs-agents`` — a minute of conversation, ``per_audio_minute`` with an
output price of 0, the shape of the STT and GPT-Live rows. The rate is the
vendor's published per-minute conversational price read on 2026-09-19
(elevenlabs.io/pricing, the paid tiers' overage); an administrator who pays
another tier edits it, as everywhere else.

Same three rules as ``f1a3c5e7b9d2``: the catalogue row is inserted only when
unknown, the tariff only when the model has NO active tariff (our retired row
re-activated on conflict), no capability invented — the provenance stays
``declared``. Production never replays the seed bundle, so what an upgraded
instance gets travels here; a guard test holds the two sources equal.
"""

from __future__ import annotations

import logging
from collections.abc import Sequence
from typing import Any

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "b7d1e3f5a9c2"
down_revision: str | None = "f1a3c5e7b9d2"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

# print() raises UnicodeEncodeError under a CP1252 Windows console (audit F047).
logger = logging.getLogger("alembic.runtime.migration")

#: Same instant as the seed bundle's row, so both sources describe ONE tariff.
EFFECTIVE_FROM = "2026-09-19T20:00:00+00:00"

#: ElevenLabs Agents: a minute of conversation, whatever agent speaks it.
_ELEVENLABS_AGENTS: dict[str, Any] = {
    "input": 0.10,
    "cached": None,
    "output": 0.0,
    "audio_input": None,
    "audio_output": None,
    "unit": "per_audio_minute",
}

#: Every live model this migration prices, with its provider and tariff.
LIVE_MODELS: dict[str, tuple[str, dict[str, Any]]] = {
    "elevenlabs-agents": ("elevenlabs", _ELEVENLABS_AGENTS),
}

#: The catalogue row of a live model: the seed bundle's defaults for a
#: speech-to-speech model (``realtime``: never offered to a chat slot).
CATALOGUE_DEFAULTS: dict[str, Any] = {
    "max_input_tokens": 8192,
    "max_output_tokens": 4096,
    "supports_tools": True,
    "supports_structured_output": True,
    "supports_strict_mode": False,
    "supports_streaming": True,
    "supports_vision": False,
    "is_reasoning_model": False,
    "supports_temperature": False,
    "supports_top_p": False,
    "supports_frequency_penalty": False,
    "supports_presence_penalty": False,
    "kind": "realtime",
    "reasoning_enum_values": None,
    "reasoning_doc_i18n_key": None,
    "is_active": True,
}

_INSERT_MODEL = sa.text("""
    INSERT INTO llm_models (
        provider, model_name, max_input_tokens, max_output_tokens,
        supports_tools, supports_structured_output, supports_strict_mode,
        supports_streaming, supports_vision, is_reasoning_model,
        supports_temperature, supports_top_p, supports_frequency_penalty,
        supports_presence_penalty, kind, reasoning_enum_values,
        reasoning_doc_i18n_key, is_active
    ) VALUES (
        :provider, :model_name, :max_input_tokens, :max_output_tokens,
        :supports_tools, :supports_structured_output, :supports_strict_mode,
        :supports_streaming, :supports_vision, :is_reasoning_model,
        :supports_temperature, :supports_top_p, :supports_frequency_penalty,
        :supports_presence_penalty, CAST(:kind AS llm_model_kind_enum),
        CAST(:reasoning_enum_values AS jsonb), :reasoning_doc_i18n_key, :is_active
    )
    ON CONFLICT (model_name) DO NOTHING
    """)

_INSERT_TARIFF = sa.text("""
    INSERT INTO llm_model_pricing (
        id, model_id, input_unit_price, cached_input_unit_price, output_unit_price,
        audio_input_unit_price, audio_output_unit_price,
        pricing_unit, effective_from, is_active, created_at, updated_at
    )
    SELECT gen_random_uuid(), m.id, :input_price, :cached_price, :output_price,
           :audio_input_price, :audio_output_price,
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

_RETIRE_TARIFF = sa.text("""
    UPDATE llm_model_pricing p
       SET is_active = false, updated_at = NOW()
      FROM llm_models m
     WHERE m.id = p.model_id
       AND m.model_name = :model_name
       AND p.effective_from = CAST(:effective_from AS timestamptz)
    """)


def upgrade() -> None:
    """Price the ElevenLabs agents where no tariff declares them."""
    bind = op.get_bind()
    for model_name, (provider, tariff) in LIVE_MODELS.items():
        bind.execute(
            _INSERT_MODEL,
            {**CATALOGUE_DEFAULTS, "provider": provider, "model_name": model_name},
        )
        inserted = bind.execute(
            _INSERT_TARIFF,
            {
                "model_name": model_name,
                "input_price": tariff["input"],
                "cached_price": tariff["cached"],
                "output_price": tariff["output"],
                "audio_input_price": tariff["audio_input"],
                "audio_output_price": tariff["audio_output"],
                "unit": tariff["unit"],
                "effective_from": EFFECTIVE_FROM,
            },
        ).rowcount
        logger.info("live pricing: %s tariff rows written=%d", model_name, inserted)


def downgrade() -> None:
    """Retire the tariff this migration may have added; the catalogue row stays (history)."""
    bind = op.get_bind()
    for model_name in LIVE_MODELS:
        bind.execute(_RETIRE_TARIFF, {"model_name": model_name, "effective_from": EFFECTIVE_FROM})
