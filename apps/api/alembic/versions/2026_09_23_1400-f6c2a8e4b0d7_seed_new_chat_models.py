"""Carry the chat models the reference seed gained on 2026-09-23 into every instance.

Revision ID: f6c2a8e4b0d7
Revises: e4a7c2f9b1d6
Create Date: 2026-09-23 14:00:00.000000

Eight chat models joined ``infrastructure/database/seeds/llm_pricing_seed.sql``
on 2026-09-23: qwen3.8-flash, qwen3.7-max, qwen3.7-flash and qwen3.6-flash
(Alibaba Model Studio, Germany (Frankfurt) grid, deployment scope Global),
gemini-3.8-flash (the price valid through 2026-12-31) and gpt-6-astra,
gpt-6-sol and gpt-6-luna (Standard processing, short context). An upgraded
instance never replays that bundle — measured on production 2026-09-23, the
API boot logs « Skipping SQL seeds » with ``APPLY_SEEDS=false`` — so they
travel here, the way ``e9b5d7f3a2c4`` carried deepseek-flash.

The same rules as that migration, all about not inventing business data
(ADR-228, ADR-244):

* a catalogue row is inserted only when the model is unknown (``ON CONFLICT
  (model_name) DO NOTHING``) — a row an administrator curated stands;
* a tariff is inserted only when the model has NO active tariff — a price an
  administrator set stands — and our own row, retired by a downgrade, is
  re-activated rather than duplicated;
* provenance ``verified``: every capability below was read by a person on the
  vendor's own model page, so ``get_effective_context_window`` trusts the
  window rather than falling back to the static table.

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
revision: str = "f6c2a8e4b0d7"
down_revision: str | None = "e4a7c2f9b1d6"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

# print() raises UnicodeEncodeError under a CP1252 Windows console (audit F047).
logger = logging.getLogger("alembic.runtime.migration")

#: Same instant as the seed bundle, so both sources describe ONE tariff row.
EFFECTIVE_FROM = "2026-09-23T00:00:00+00:00"
#: The same instant as a bound value: asyncpg refuses a string for a
#: ``timestamptz`` parameter where psycopg casts it.
EFFECTIVE_FROM_AT = datetime.fromisoformat(EFFECTIVE_FROM)
PRICING_UNIT = "per_1m_tokens"
#: Read by a person on each vendor's model page (see the module docstring).
PROVENANCE = "verified"

#: Qwen (Model Studio model pages): thinking, function calling and structured
#: output; DashScope refuses ``frequency_penalty`` — the seed rows' flags.
_QWEN_FLAGS: dict[str, Any] = {
    "provider": "qwen",
    "supports_tools": True,
    "supports_structured_output": True,
    "supports_strict_mode": False,
    "supports_streaming": True,
    "is_reasoning_model": True,
    "supports_temperature": True,
    "supports_top_p": True,
    "supports_frequency_penalty": False,
    "supports_presence_penalty": True,
    "kind": "chat",
    "reasoning_enum_values": None,
    "is_active": True,
}
#: Gemini 3.x flash, as the seed's gemini-3.7-flash row describes the family.
_GEMINI_FLAGS: dict[str, Any] = {
    "provider": "gemini",
    "supports_tools": True,
    "supports_structured_output": True,
    "supports_strict_mode": False,
    "supports_streaming": True,
    "supports_vision": True,
    "is_reasoning_model": True,
    "supports_temperature": True,
    "supports_top_p": True,
    "supports_frequency_penalty": True,
    "supports_presence_penalty": True,
    "kind": "chat",
    "reasoning_doc_i18n_key": None,
    "is_active": True,
}
#: GPT-6 (OpenAI model pages): a reasoning model, so no sampling parameter.
_GPT6_FLAGS: dict[str, Any] = {
    "provider": "openai",
    "max_input_tokens": 922_000,
    "max_output_tokens": 128_000,
    "supports_tools": True,
    "supports_structured_output": True,
    "supports_strict_mode": True,
    "supports_streaming": True,
    "supports_vision": True,
    "is_reasoning_model": True,
    "supports_temperature": False,
    "supports_top_p": False,
    "supports_frequency_penalty": False,
    "supports_presence_penalty": False,
    "kind": "chat",
    "reasoning_doc_i18n_key": None,
    "is_active": True,
}
_GPT6_LADDER: list[str] = ["none", "low", "medium", "high", "xhigh", "max"]

#: One entry per model, column names the seed's.
CATALOGUE_ROWS: tuple[dict[str, Any], ...] = (
    {
        **_QWEN_FLAGS,
        "model_name": "qwen3.8-flash",
        "max_input_tokens": 991_808,
        "max_output_tokens": 131_072,
        "supports_vision": True,
        "reasoning_doc_i18n_key": "qwen3_8",
    },
    {
        **_QWEN_FLAGS,
        "model_name": "qwen3.7-max",
        "max_input_tokens": 991_808,
        "max_output_tokens": 131_072,
        "supports_vision": False,
        "reasoning_doc_i18n_key": "qwen3_7",
    },
    {
        **_QWEN_FLAGS,
        "model_name": "qwen3.7-flash",
        "max_input_tokens": 991_808,
        "max_output_tokens": 131_072,
        "supports_vision": True,
        "reasoning_doc_i18n_key": "qwen3_7",
    },
    {
        **_QWEN_FLAGS,
        "model_name": "qwen3.6-flash",
        "max_input_tokens": 991_808,
        "max_output_tokens": 65_536,
        "supports_vision": True,
        "reasoning_doc_i18n_key": "qwen3_6",
    },
    {
        **_GEMINI_FLAGS,
        "model_name": "gemini-3.8-flash",
        "max_input_tokens": 1_048_576,
        "max_output_tokens": 65_536,
        # ``minimal`` "returns an error": the narrowing keeps a slot from sending it.
        "reasoning_enum_values": ["low", "medium", "high"],
    },
    {
        **_GPT6_FLAGS,
        "model_name": "gpt-6-astra",
        # No off switch on Astra.
        "reasoning_enum_values": ["low", "medium", "high", "xhigh", "max"],
    },
    {**_GPT6_FLAGS, "model_name": "gpt-6-sol", "reasoning_enum_values": _GPT6_LADDER},
    {**_GPT6_FLAGS, "model_name": "gpt-6-luna", "reasoning_enum_values": _GPT6_LADDER},
)

#: USD per 1M tokens: (input, cached input, output) — the seed bundle's rows.
TARIFFS: dict[str, tuple[float, float, float]] = {
    "qwen3.8-flash": (0.113, 0.0113, 0.382),
    "qwen3.7-max": (1.65, 0.33, 4.951),
    "qwen3.7-flash": (0.028, 0.0056, 0.11),
    "qwen3.6-flash": (0.165, 0.0165, 0.99),
    "gemini-3.8-flash": (0.75, 0.075, 3.75),
    "gpt-6-astra": (10.0, 1.0, 50.0),
    "gpt-6-sol": (2.0, 0.2, 10.0),
    "gpt-6-luna": (0.1, 0.01, 0.5),
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
    logger.info("new chat models: %d catalogue rows added, %d tariffs set", added, priced)


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
