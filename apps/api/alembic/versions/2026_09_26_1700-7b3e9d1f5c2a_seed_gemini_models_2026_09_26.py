"""Carry the Gemini models the reference seed gained on 2026-09-26 into every instance.

Revision ID: 7b3e9d1f5c2a
Revises: d79c9fc26844
Create Date: 2026-09-26 17:00:00.000000

Four Gemini models joined ``infrastructure/database/seeds/llm_pricing_seed.sql``
on 2026-09-26, each read on its page under ai.google.dev/gemini-api/docs/models
and priced from ai.google.dev/gemini-api/docs/pricing (Standard paid tier):
gemini-3.1-flash-lite (the stable release of the preview the catalogue already
holds) and three speech models, gemini-3.8-flash-tts, gemini-3.8-flash-lite-tts
and gemini-3.1-flash-tts-preview. A speech model bills TEXT in on the input
axis and AUDIO out on the output axis, as the vendor's usage report counts
them. The two 3.8 speech models carry the price valid through 2026-12-31: it
doubles on 2027-01-01 and nothing switches it (one active tariff per model).

An upgraded instance never replays the seed bundle (``APPLY_SEEDS=false`` in
production), so the models travel here, under the rules of ``f6c2a8e4b0d7``:

* a catalogue row is inserted only when the model is unknown (``ON CONFLICT
  (model_name) DO NOTHING``) — a row an administrator curated stands;
* a tariff is inserted only when the model has NO active tariff — a price an
  administrator set stands — and our own row, retired by a downgrade, is
  re-activated rather than duplicated;
* provenance ``verified``: every capability below was read by a person on the
  vendor's own model page, so ``get_effective_context_window`` trusts it.

The values mirror the seed bundle row for row (same ``effective_from``, so the
bundle's upsert lands on the same row on a fresh install, where this migration
runs first); a guard test holds the two sources equal.
"""

from __future__ import annotations

import json
import logging
from collections.abc import Sequence
from datetime import datetime
from typing import Any

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "7b3e9d1f5c2a"
down_revision: str | None = "d79c9fc26844"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

# print() raises UnicodeEncodeError under a CP1252 Windows console (audit F047).
logger = logging.getLogger("alembic.runtime.migration")

#: Same instant as the seed bundle, so both sources describe ONE tariff row.
EFFECTIVE_FROM = "2026-09-26T00:00:00+00:00"
#: The same instant as a bound value: asyncpg refuses a string for a
#: ``timestamptz`` parameter where psycopg casts it.
EFFECTIVE_FROM_AT = datetime.fromisoformat(EFFECTIVE_FROM)
PRICING_UNIT = "per_1m_tokens"
#: Read by a person on each vendor's model page (see the module docstring).
PROVENANCE = "verified"

#: A Gemini speech model (model pages): text in, audio out, 8 192 tokens in and
#: 16 384 out, no function calling, no structured output, no thinking and no
#: sampling parameter. ``supports_streaming`` is stated by no page: it follows
#: every other speech row of the bundle, and nothing reads it for a speech model.
_SPEECH_FLAGS: dict[str, Any] = {
    "provider": "gemini",
    "max_input_tokens": 8_192,
    "max_output_tokens": 16_384,
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

#: One entry per model, column names the seed's.
CATALOGUE_ROWS: tuple[dict[str, Any], ...] = (
    {
        "provider": "gemini",
        "model_name": "gemini-3.1-flash-lite",
        "max_input_tokens": 1_048_576,
        "max_output_tokens": 65_536,
        "supports_tools": True,
        "supports_structured_output": True,
        "supports_strict_mode": False,
        "supports_streaming": True,
        "supports_vision": True,
        "is_reasoning_model": True,
        "supports_temperature": True,
        "supports_top_p": True,
        # No penalty, like every Gemini 3.1 row of the catalogue.
        "supports_frequency_penalty": False,
        "supports_presence_penalty": False,
        "kind": "chat",
        # « Thinking: Supported » on the model page, which lists no level, and
        # the thinking guide's table omits this model: the ladder is the
        # preview's, corroborated by langchain-google-genai's model profile.
        "reasoning_enum_values": ["minimal", "low", "medium", "high"],
        "reasoning_doc_i18n_key": None,
        "is_active": True,
    },
    {**_SPEECH_FLAGS, "model_name": "gemini-3.8-flash-tts"},
    {**_SPEECH_FLAGS, "model_name": "gemini-3.8-flash-lite-tts"},
    {**_SPEECH_FLAGS, "model_name": "gemini-3.1-flash-tts-preview"},
)

#: USD per 1M tokens: (input, cached input, output) — the seed bundle's rows.
#: ``None`` where the vendor publishes no cache price.
TARIFFS: dict[str, tuple[float, float | None, float]] = {
    "gemini-3.1-flash-lite": (0.25, 0.025, 1.5),
    "gemini-3.8-flash-tts": (0.5, 0.125, 9.0),
    "gemini-3.8-flash-lite-tts": (0.5, 0.125, 6.0),
    "gemini-3.1-flash-tts-preview": (1.0, None, 20.0),
}

#: ``id`` and the timestamps are written explicitly: the ORM declares only
#: client-side defaults for them, so a schema built from the models (the
#: integration tests') has no server default to fall back on.
INSERT_MODEL = sa.text("""
    INSERT INTO llm_models (
        id, created_at, updated_at,
        provider, model_name, max_input_tokens, max_output_tokens,
        supports_tools, supports_structured_output, supports_strict_mode,
        supports_streaming, supports_vision, is_reasoning_model,
        supports_temperature, supports_top_p, supports_frequency_penalty,
        supports_presence_penalty, kind, reasoning_enum_values,
        reasoning_doc_i18n_key, is_active, capability_provenance
    ) VALUES (
        gen_random_uuid(), NOW(), NOW(),
        :provider, :model_name, :max_input_tokens, :max_output_tokens,
        :supports_tools, :supports_structured_output, :supports_strict_mode,
        :supports_streaming, :supports_vision, :is_reasoning_model,
        :supports_temperature, :supports_top_p, :supports_frequency_penalty,
        :supports_presence_penalty, CAST(:kind AS llm_model_kind_enum),
        CAST(:reasoning_enum_values AS jsonb), :reasoning_doc_i18n_key, :is_active,
        CAST(:capability_provenance AS llm_capability_provenance_enum)
    )
    ON CONFLICT (model_name) DO NOTHING
    """)

INSERT_TARIFF = sa.text("""
    INSERT INTO llm_model_pricing (
        id, model_id, input_unit_price, cached_input_unit_price, output_unit_price,
        pricing_unit, effective_from, is_active, created_at, updated_at
    )
    SELECT gen_random_uuid(), m.id, :input_price, :cached_price, :output_price,
           CAST(:unit AS pricing_unit_enum), :effective_from,
           true, NOW(), NOW()
      FROM llm_models m
     WHERE m.model_name = :model_name
       AND NOT EXISTS (
           SELECT 1 FROM llm_model_pricing p WHERE p.model_id = m.id AND p.is_active
       )
    ON CONFLICT (model_id, effective_from) DO UPDATE
       SET is_active = true, updated_at = NOW()
    """)

RETIRE_TARIFF = sa.text("""
    UPDATE llm_model_pricing p
       SET is_active = false, updated_at = NOW()
      FROM llm_models m
     WHERE m.id = p.model_id
       AND m.model_name = :model_name
       AND p.effective_from = :effective_from
       AND p.is_active
    """)


def model_params(row: dict[str, Any]) -> dict[str, Any]:
    """The bind parameters of one catalogue row.

    Args:
        row: An entry of :data:`CATALOGUE_ROWS`.

    Returns:
        The row with its ladder serialised and its provenance added.
    """
    ladder = row["reasoning_enum_values"]
    return {
        **row,
        "reasoning_enum_values": None if ladder is None else json.dumps(ladder),
        "capability_provenance": PROVENANCE,
    }


def tariff_params(model_name: str) -> dict[str, Any]:
    """The bind parameters of one model's tariff.

    Args:
        model_name: A key of :data:`TARIFFS`.

    Returns:
        The parameters :data:`INSERT_TARIFF` takes.
    """
    input_price, cached_price, output_price = TARIFFS[model_name]
    return {
        "model_name": model_name,
        "input_price": input_price,
        "cached_price": cached_price,
        "output_price": output_price,
        "unit": PRICING_UNIT,
        "effective_from": EFFECTIVE_FROM_AT,
    }


def upgrade() -> None:
    """Add each model where unknown, and price it where it has no active tariff."""
    bind = op.get_bind()
    added = sum(bind.execute(INSERT_MODEL, model_params(row)).rowcount for row in CATALOGUE_ROWS)
    priced = sum(bind.execute(INSERT_TARIFF, tariff_params(name)).rowcount for name in TARIFFS)
    logger.info("gemini models 2026-09-26: %d catalogue rows added, %d tariffs set", added, priced)


def downgrade() -> None:
    """Retire the tariffs this migration may have added; the catalogue rows stay.

    Retiring keeps history (the seed bundle's doctrine), and a catalogue row
    with no active tariff is exactly the state the upgrade found for a model it
    had to add. A catalogue row is not deleted: an administrator may have
    configured a slot on it since, and deactivating a referenced model is the
    trap ADR-244 names.
    """
    bind = op.get_bind()
    for name in TARIFFS:
        bind.execute(RETIRE_TARIFF, {"model_name": name, "effective_from": EFFECTIVE_FROM_AT})
