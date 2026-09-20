"""ElevenLabs leaves the tariff table as an agents platform; v3 Conversational joins it as a TTS model.

Revision ID: a4c8e1f7b3d5
Revises: c9e2a4b6d8f1
Create Date: 2026-09-20 12:00:00.000000

Two price grids at ElevenLabs (owner rule 2026-09-20): the SIMPLE API
(speech to text, text to speech — what the platform's STT and TTS slots run
on the deployment's key and price through this table) and the AGENTS API
(telephony, the live mode — on the PERSON's own key, priced by nobody here:
the vendor states its bill and the app shows it). ``b7d1e3f5a9c2`` had put
the agents platform IN the table under one flat row, ``elevenlabs-agents``
— a guess at a price the platform never pays. This migration retires that
tariff (kept as history, ``is_active = false``) and DEACTIVATES its catalogue
row (a ``realtime`` model no slot may run), and declares
``eleven_v3_conversational`` for the voice-synthesis slot at the simple
API's price: 0.05 USD per 1 000 characters, encoded like every TTS row of
the bundle (``per_1m_tokens`` with characters as tokens — 50 USD per
million), the five-thousand-character request limit the models API states
(measured on the owner's key 2026-09-20).

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
revision: str = "a4c8e1f7b3d5"
down_revision: str | None = "c9e2a4b6d8f1"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

# print() raises UnicodeEncodeError under a CP1252 Windows console (audit F047).
logger = logging.getLogger("alembic.runtime.migration")

#: Same instant as the seed bundle's row, so both sources describe ONE tariff.
EFFECTIVE_FROM = "2026-09-20T12:00:00+00:00"
#: Eleven v3 Conversational on the simple API: 0.05 USD per 1 000 characters.
_V3_CONVERSATIONAL: dict[str, Any] = {
    "input": 50.0,
    "cached": None,
    "output": 0.0,
    "audio_input": None,
    "audio_output": None,
    "unit": "per_1m_tokens",
}
#: Every model this migration prices, with its provider and tariff.
LIVE_MODELS: dict[str, tuple[str, dict[str, Any]]] = {
    "eleven_v3_conversational": ("elevenlabs", _V3_CONVERSATIONAL),
}
#: The flat row this migration retires: what ``b7d1e3f5a9c2`` wrote, kept as history.
SUPERSEDED: dict[str, dict[str, Any]] = {
    "elevenlabs-agents": {
        "input": 0.10,
        "output": 0.0,
        "effective_from": "2026-09-19T20:00:00+00:00",
    },
}
#: The catalogue rows this migration deactivates: the agents platform is no
#: model of the table (a ``realtime`` row no slot may run), kept as history.
RETIRED_CATALOGUE: tuple[str, ...] = ("elevenlabs-agents",)
#: The catalogue row of a TTS model: the seed bundle's shape for ElevenLabs'
#: text-to-speech rows (``tts``: offered to the voice-synthesis slot alone).
CATALOGUE_DEFAULTS: dict[str, Any] = {
    "max_input_tokens": 5000,
    "max_output_tokens": 1,
    "supports_tools": False,
    "supports_structured_output": False,
    "supports_strict_mode": False,
    "supports_streaming": True,
    "supports_vision": False,
    "is_reasoning_model": False,
    "supports_temperature": False,
    "supports_top_p": False,
    "supports_frequency_penalty": False,
    "supports_presence_penalty": False,
    "kind": "tts",
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

_SET_TARIFF_ACTIVE = sa.text("""
    UPDATE llm_model_pricing p
       SET is_active = :active, updated_at = NOW()
      FROM llm_models m
     WHERE m.id = p.model_id
       AND m.model_name = :model_name
       AND p.effective_from = CAST(:effective_from AS timestamptz)
    """)

_SET_MODEL_ACTIVE = sa.text("""
    UPDATE llm_models SET is_active = :active, updated_at = NOW()
     WHERE model_name = :model_name
    """)


def upgrade() -> None:
    """Price v3 Conversational for the TTS slot; take the agents platform out of the table."""
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
    for model_name, old in SUPERSEDED.items():
        retired = bind.execute(
            _SET_TARIFF_ACTIVE,
            {"model_name": model_name, "effective_from": old["effective_from"], "active": False},
        ).rowcount
        logger.info("live pricing: %s flat tariff rows retired=%d", model_name, retired)
    for model_name in RETIRED_CATALOGUE:
        bind.execute(_SET_MODEL_ACTIVE, {"model_name": model_name, "active": False})


def downgrade() -> None:
    """Retire v3 Conversational's tariff; put the agents platform back as it was."""
    bind = op.get_bind()
    for model_name in LIVE_MODELS:
        bind.execute(
            _SET_TARIFF_ACTIVE,
            {"model_name": model_name, "effective_from": EFFECTIVE_FROM, "active": False},
        )
    for model_name, old in SUPERSEDED.items():
        bind.execute(
            _SET_TARIFF_ACTIVE,
            {"model_name": model_name, "effective_from": old["effective_from"], "active": True},
        )
    for model_name in RETIRED_CATALOGUE:
        bind.execute(_SET_MODEL_ACTIVE, {"model_name": model_name, "active": True})
