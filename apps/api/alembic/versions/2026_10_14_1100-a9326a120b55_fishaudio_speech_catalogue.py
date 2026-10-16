"""Fish Audio's speech models join the catalogue; the ElevenLabs v4 pair reaches upgraded instances.

Revision ID: a9326a120b55
Revises: cec87eda4868
Create Date: 2026-10-14 11:00:00.000000

Fish Audio bills speech synthesis per million UTF-8 BYTES of text (its pricing
page, read 2026-10-13): ``s2.1-pro``, ``s2-pro`` and ``s1`` at 15 USD,
``s2.1-pro-free`` at 0, and ``drama-3`` at 10 USD (owner decision 2026-10-14 —
the vendor publishes no price for it). Encoded like every TTS row of the bundle:
``per_1m_tokens`` with the billed unit as tokens — here bytes, which the
``fishaudio`` voice family counts (ADR-345). Its two transcription models,
``transcribe-1`` and ``transcribe-1-pro``, cost 0.36 USD per audio hour each, on
the duration rounded up to the second — an ``audio`` row like every remote
speech-to-text engine of the bundle.

The one retirement the vendor announces travels in ``deprecation_date``, the
column the catalogue's retirement predicates read and the admin shows as « the
provider published a retirement date »: ``s1`` retires on 2026-12-31 (served and
billed as ``s2.1-pro`` afterwards — ``VENDOR_SHUTDOWNS`` declares it). The free
model costs nothing « through November 30, 2026 » (the vendor's changelog of
2026-06-23), which is a price, not a retirement: no date is stored for it, and
what it costs past that day is the vendor's to state. The vendor states no
request length, so a Fish row keeps the column's default window and its
provenance stays ``declared``: nothing invented.

``eleven_v4`` and ``eleven_v4_turbo`` joined the seed bundle in v2.1.0 without a
migration, so an instance upgraded by migrations never received them; they
travel here under the same rules.

Same three rules as ``a4c8e1f7b3d5``: the catalogue row is inserted only when
unknown, the tariff only when the model has NO active tariff, the deprecation
date only where none is stated yet — an administrator's own row is never
overwritten. Production never replays the seed bundle, so what an upgraded
instance gets travels here; a guard test holds the two sources equal.
"""

from __future__ import annotations

import logging
from collections.abc import Sequence
from typing import Any

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "a9326a120b55"
down_revision: str | None = "cec87eda4868"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

# print() raises UnicodeEncodeError under a CP1252 Windows console (audit F047).
logger = logging.getLogger("alembic.runtime.migration")

#: Same instant as the seed bundle's rows, so both sources describe ONE tariff:
#: the day both vendors' pages were read.
EFFECTIVE_FROM = "2026-10-13T00:00:00+00:00"


def _per_million(input_price: float) -> dict[str, Any]:
    """A text-billed speech tariff: the billed unit on the input axis."""
    return {
        "input": input_price,
        "cached": None,
        "output": 0.0,
        "audio_input": None,
        "audio_output": None,
        "unit": "per_1m_tokens",
    }


def _per_audio_hour(input_price: float) -> dict[str, Any]:
    """A transcription tariff: the audio's duration, priced per hour on the input axis."""
    return {**_per_million(input_price), "unit": "per_audio_hour"}


#: Every model this migration prices, with its provider and tariff.
LIVE_MODELS: dict[str, tuple[str, dict[str, Any]]] = {
    "s2.1-pro": ("fishaudio", _per_million(15.0)),
    "s2.1-pro-free": ("fishaudio", _per_million(0.0)),
    "s2-pro": ("fishaudio", _per_million(15.0)),
    "s1": ("fishaudio", _per_million(15.0)),
    "drama-3": ("fishaudio", _per_million(10.0)),
    "transcribe-1": ("fishaudio", _per_audio_hour(0.36)),
    "transcribe-1-pro": ("fishaudio", _per_audio_hour(0.36)),
    # ElevenLabs API pricing after the offer that ended 2026-10-12 (the seed's rows).
    "eleven_v4": ("elevenlabs", _per_million(80.0)),
    "eleven_v4_turbo": ("elevenlabs", _per_million(40.0)),
}
#: The catalogue row of a TTS model: the seed bundle's shape for every
#: text-to-speech row (``tts``: offered to the voice-synthesis slots alone).
CATALOGUE_DEFAULTS: dict[str, Any] = {
    "max_input_tokens": 8192,
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
#: A transcription row: the seed bundle's shape for every remote speech-to-text
#: engine (``audio``: offered to the transcription slot alone, nothing streamed).
_TRANSCRIPTION: dict[str, Any] = {
    "max_input_tokens": 1,
    "supports_streaming": False,
    "kind": "audio",
}
#: The columns a model states apart from the defaults: the request limits
#: ElevenLabs' models API states (the seed's values), and the transcription rows.
CATALOGUE_OVERRIDES: dict[str, dict[str, Any]] = {
    "eleven_v4": {"max_input_tokens": 10000},
    "eleven_v4_turbo": {"max_input_tokens": 5000},
    "transcribe-1": _TRANSCRIPTION,
    "transcribe-1-pro": _TRANSCRIPTION,
}
#: The retirement dates the vendor states.
DEPRECATIONS: dict[str, str] = {
    "s1": "2026-12-31",
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
        CAST(:provider AS llm_provider_enum), :model_name, :max_input_tokens,
        :max_output_tokens, :supports_tools, :supports_structured_output,
        :supports_strict_mode, :supports_streaming, :supports_vision,
        :is_reasoning_model, :supports_temperature, :supports_top_p,
        :supports_frequency_penalty, :supports_presence_penalty,
        CAST(:kind AS llm_model_kind_enum), CAST(:reasoning_enum_values AS jsonb),
        :reasoning_doc_i18n_key, :is_active
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

_SET_DEPRECATION = sa.text("""
    UPDATE llm_models
       SET deprecation_date = CAST(:deprecation_date AS date), updated_at = NOW()
     WHERE model_name = :model_name
       AND deprecation_date IS NULL
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
    """Declare and price the speech models; state the vendors' retirement dates."""
    bind = op.get_bind()
    for model_name, (provider, tariff) in LIVE_MODELS.items():
        bind.execute(
            _INSERT_MODEL,
            {
                **CATALOGUE_DEFAULTS,
                **CATALOGUE_OVERRIDES.get(model_name, {}),
                "provider": provider,
                "model_name": model_name,
            },
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
        logger.info("speech catalogue: %s tariff rows written=%d", model_name, inserted)
    for model_name, deprecation_date in DEPRECATIONS.items():
        bind.execute(
            _SET_DEPRECATION, {"model_name": model_name, "deprecation_date": deprecation_date}
        )


def downgrade() -> None:
    """Retire this migration's tariffs; the catalogue rows stay, as history."""
    bind = op.get_bind()
    for model_name in LIVE_MODELS:
        bind.execute(_RETIRE_TARIFF, {"model_name": model_name, "effective_from": EFFECTIVE_FROM})
