"""Audio rates on a tariff, and the live models priced (ADR-300 wave 3).

Revision ID: f1a3c5e7b9d2
Revises: d7f2a4c6e8b1
Create Date: 2026-09-19 15:00:00.000000

A speech-to-speech model bills its audio at a rate of its own, next to its
text rate, per million tokens — the tariff row could only say one. Two
nullable columns join ``llm_model_pricing``: ``audio_input_unit_price`` and
``audio_output_unit_price``, in the row's ``pricing_unit``. NULL on both
means « no audio rate declared » (every existing row); a model billed by the
minute (``per_audio_minute``) keeps them NULL, its unit already says it all.

The live models the person's key discovers are then priced, the way the
deepseek-flash migration priced a model production had created by hand
(``e9b5d7f3a2c4``): production never replays the reference SQL seed bundle,
so what an upgraded instance gets travels here, and a guard test holds the
two sources equal. Rates read on 2026-09-19 from the vendors' published
tables (ai.google.dev/gemini-api/docs/pricing, openai.com/api/pricing):

* Gemini 3.8 Live, 3.8 Live Extended Thinking, 3.1 Flash Live: text 0.75 in /
  4.50 out, audio 3.00 in / 12.00 out — USD per 1M tokens;
* Gemini 2.5 Flash native audio: text 0.50 / 2.00, audio 3.00 / 12.00. The
  reference bundle carried 1.00 / 2.50 for the ``preview-09-2025`` name: that
  tariff is retired and replaced ONLY where the active row is exactly the
  bundle's (same instant, same three prices) — a price an administrator
  typed stands, as everywhere else in this file;
* GPT-Live: 0.05 USD per minute, billed per second, transcripts included —
  ``per_audio_minute`` with an output price of 0, the shape of the STT rows.

Three rules, unchanged from ``e9b5d7f3a2c4``: a catalogue row is inserted
only when the model is unknown (``ON CONFLICT (model_name) DO NOTHING``); a
tariff is inserted only when the model has NO active tariff, and when OUR
row already exists retired the conflict re-activates it; nothing here
invents a capability — the token limits are the catalogue's defaults, so the
provenance stays ``declared`` (the column's own default), exactly what the
seed bundle's INSERT produces.
"""

from __future__ import annotations

import logging
from collections.abc import Sequence
from typing import Any

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "f1a3c5e7b9d2"
down_revision: str | None = "d7f2a4c6e8b1"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

# print() raises UnicodeEncodeError under a CP1252 Windows console (audit F047).
logger = logging.getLogger("alembic.runtime.migration")

_AUDIO_INPUT_COMMENT = (
    "Audio input unit price in USD (NULL if the model bills no audio at a rate of its "
    "own; semantic = pricing_unit)"
)
_AUDIO_OUTPUT_COMMENT = (
    "Audio output unit price in USD (NULL if the model bills no audio at a rate of its "
    "own; semantic = pricing_unit)"
)

#: Same instant as the seed bundle's live rows, so both sources describe ONE
#: tariff row per model on a fresh install.
EFFECTIVE_FROM = "2026-09-19T14:00:00+00:00"

#: The Gemini 3.x live tier — one published tariff for the three names.
_GEMINI_LIVE_3X: dict[str, Any] = {
    "input": 0.75,
    "cached": None,
    "output": 4.5,
    "audio_input": 3.0,
    "audio_output": 12.0,
    "unit": "per_1m_tokens",
}
#: The Gemini 2.5 Flash native-audio tier, three names of one model.
_GEMINI_NATIVE_AUDIO_25: dict[str, Any] = {
    "input": 0.5,
    "cached": None,
    "output": 2.0,
    "audio_input": 3.0,
    "audio_output": 12.0,
    "unit": "per_1m_tokens",
}
#: GPT-Live: a minute of session, whatever is said in it.
_GPT_LIVE: dict[str, Any] = {
    "input": 0.05,
    "cached": None,
    "output": 0.0,
    "audio_input": None,
    "audio_output": None,
    "unit": "per_audio_minute",
}

#: Every live model this migration prices, with its provider and tariff.
LIVE_MODELS: dict[str, tuple[str, dict[str, Any]]] = {
    "gemini-3.8-live": ("gemini", _GEMINI_LIVE_3X),
    "gemini-3.8-live-extended-thinking": ("gemini", _GEMINI_LIVE_3X),
    "gemini-3.1-flash-live-preview": ("gemini", _GEMINI_LIVE_3X),
    "gemini-2.5-flash-native-audio-preview-09-2025": ("gemini", _GEMINI_NATIVE_AUDIO_25),
    "gemini-2.5-flash-native-audio-preview-12-2025": ("gemini", _GEMINI_NATIVE_AUDIO_25),
    "gemini-2.5-flash-native-audio-latest": ("gemini", _GEMINI_NATIVE_AUDIO_25),
    "gpt-live-1": ("openai", _GPT_LIVE),
}

#: The catalogue row of a live model: the seed bundle's own defaults for a
#: speech-to-speech model (the ``realtime`` kind is required by no slot, so a
#: live model is never offered to a chat slot).
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

#: The bundle's OLD tariff for the 2.5 native-audio name it already carried:
#: an active row equal to it, to the instant, is ours and may be retired.
SUPERSEDED: dict[str, dict[str, Any]] = {
    "gemini-2.5-flash-native-audio-preview-09-2025": {
        "input": 1.0,
        "output": 2.5,
        "effective_from": "2026-03-19T00:08:59.327299+00:00",
    },
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

_RETIRE_SUPERSEDED = sa.text("""
    UPDATE llm_model_pricing p
       SET is_active = false, updated_at = NOW()
      FROM llm_models m
     WHERE m.id = p.model_id
       AND m.model_name = :model_name
       AND p.is_active
       AND p.effective_from = CAST(:effective_from AS timestamptz)
       AND p.input_unit_price = :input_price
       AND p.cached_input_unit_price IS NULL
       AND p.output_unit_price = :output_price
       AND p.audio_input_unit_price IS NULL
       AND p.audio_output_unit_price IS NULL
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
    """Add the two audio columns, then price every live model that has no tariff."""
    op.add_column(
        "llm_model_pricing",
        sa.Column(
            "audio_input_unit_price",
            sa.DECIMAL(precision=10, scale=6),
            nullable=True,
            comment=_AUDIO_INPUT_COMMENT,
        ),
    )
    op.add_column(
        "llm_model_pricing",
        sa.Column(
            "audio_output_unit_price",
            sa.DECIMAL(precision=10, scale=6),
            nullable=True,
            comment=_AUDIO_OUTPUT_COMMENT,
        ),
    )

    bind = op.get_bind()
    for model_name, (provider, tariff) in LIVE_MODELS.items():
        bind.execute(
            _INSERT_MODEL,
            {**CATALOGUE_DEFAULTS, "provider": provider, "model_name": model_name},
        )
        superseded = SUPERSEDED.get(model_name)
        if superseded is not None:
            retired = bind.execute(
                _RETIRE_SUPERSEDED,
                {
                    "model_name": model_name,
                    "effective_from": superseded["effective_from"],
                    "input_price": superseded["input"],
                    "output_price": superseded["output"],
                },
            ).rowcount
            logger.info("live pricing: %s superseded rows retired=%d", model_name, retired)
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
    """Retire the tariffs this migration may have added, then drop the columns.

    Retiring keeps history (the doctrine of the seed bundle); the catalogue
    rows stay, as ``e9b5d7f3a2c4``'s does. A superseded row retired on the
    way up is not re-activated: the instance would then be billing the
    1.00 / 2.50 tariff the vendor no longer publishes.
    """
    bind = op.get_bind()
    for model_name in LIVE_MODELS:
        bind.execute(_RETIRE_TARIFF, {"model_name": model_name, "effective_from": EFFECTIVE_FROM})
    op.drop_column("llm_model_pricing", "audio_output_unit_price")
    op.drop_column("llm_model_pricing", "audio_input_unit_price")
