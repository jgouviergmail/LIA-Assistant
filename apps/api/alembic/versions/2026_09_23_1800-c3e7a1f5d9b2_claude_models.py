"""Carry the Claude models the reference seed gained on 2026-09-23 into every instance.

Revision ID: c3e7a1f5d9b2
Revises: a9d3f1c7e5b2
Create Date: 2026-09-23 18:00:00.000000

Eight Claude models the Claude API serves were missing from the catalogue
(ADR-306): claude-fable-5-1, claude-fable-5, claude-opus-5-5, claude-opus-5,
claude-sonnet-5, claude-opus-4-8, claude-opus-4-7 and claude-sonnet-4-5. An
upgraded instance never replays the seed bundle (``APPLY_SEEDS=false`` in
production), so they travel here, the way ``f6c2a8e4b0d7`` carried the Qwen,
Gemini and GPT-6 models.

The same rules as that migration, all about not inventing business data
(ADR-228, ADR-244):

* a catalogue row is inserted only when the model is unknown (``ON CONFLICT
  (model_name) DO NOTHING``) -- a row an administrator curated stands;
* a tariff is inserted only when the model has NO active tariff -- a price an
  administrator set stands -- and our own row, retired by a downgrade, is
  re-activated rather than duplicated;
* provenance ``verified``: the windows and effort ladders were read on the
  Models API, the sampling and thinking facts measured by validation requests
  on the API itself (``core/claude_surface.py`` holds them), the prices on the
  vendor's pricing page -- so ``get_effective_context_window`` trusts the
  window rather than falling back to the static table.

The values mirror the seed bundle row for row (same ``effective_from``, so the
bundle's upsert lands on the same row on a fresh install, where this migration
runs first); a guard test holds the two sources equal, and holds every row
against the Claude surface declaration.
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
revision: str = "c3e7a1f5d9b2"
down_revision: str | None = "a9d3f1c7e5b2"
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
#: Read and measured by a person (see the module docstring).
PROVENANCE = "verified"

#: Every generation from Opus 4.7 on: 1M in / 128K out, vision, tools and
#: structured output; a non-default temperature is refused (400), and top_p
#: never reaches a Claude model (the adapter drops it). Strict mode is an
#: OpenAI flag LIA never sends to another provider.
_CLAUDE_FLAGS: dict[str, Any] = {
    "provider": "anthropic",
    "max_input_tokens": 1_000_000,
    "max_output_tokens": 128_000,
    "supports_tools": True,
    "supports_structured_output": True,
    "supports_strict_mode": False,
    "supports_streaming": True,
    "supports_vision": True,
    "is_reasoning_model": True,
    "supports_temperature": False,
    "supports_top_p": False,
    "supports_frequency_penalty": False,
    "supports_presence_penalty": False,
    "kind": "chat",
    "is_active": True,
}
#: The Models API's effort ladder. Fable 5, Fable 5.1 and Opus 5.5 cannot switch
#: thinking off, so their ladder has no ``none``.
_ALWAYS_ON_LADDER: list[str] = ["low", "medium", "high", "xhigh", "max"]
_SWITCHABLE_LADDER: list[str] = ["none", *_ALWAYS_ON_LADDER]

#: One entry per model, column names the seed's.
CATALOGUE_ROWS: tuple[dict[str, Any], ...] = (
    *(
        {
            **_CLAUDE_FLAGS,
            "model_name": name,
            "reasoning_enum_values": _ALWAYS_ON_LADDER,
            "reasoning_doc_i18n_key": "anthropic_always_on",
        }
        for name in ("claude-fable-5-1", "claude-fable-5", "claude-opus-5-5")
    ),
    *(
        {
            **_CLAUDE_FLAGS,
            "model_name": name,
            "reasoning_enum_values": _SWITCHABLE_LADDER,
            "reasoning_doc_i18n_key": "anthropic_5",
        }
        for name in ("claude-opus-5", "claude-sonnet-5")
    ),
    *(
        {
            **_CLAUDE_FLAGS,
            "model_name": name,
            "reasoning_enum_values": _SWITCHABLE_LADDER,
            "reasoning_doc_i18n_key": "anthropic_4_7",  # gitleaks:allow
        }
        for name in ("claude-opus-4-8", "claude-opus-4-7")
    ),
    {
        # A 200K window (the context-windows documentation; the Models API
        # reports 1M), budget thinking, and it still takes a temperature.
        **_CLAUDE_FLAGS,
        "model_name": "claude-sonnet-4-5",
        "max_input_tokens": 200_000,
        "max_output_tokens": 64_000,
        "supports_temperature": True,
        "reasoning_enum_values": None,
        "reasoning_doc_i18n_key": "anthropic_4_5",  # gitleaks:allow
    },
)

#: USD per 1M tokens: (input, cache hits and refreshes, output) -- the seed
#: bundle's rows. A cache WRITE carries no price of its own: it is a multiplier
#: of the input price (1.25x on the 5-minute TTL), applied by the cost
#: computation (ADR-306).
TARIFFS: dict[str, tuple[float, float, float]] = {
    "claude-fable-5-1": (10.0, 0.25, 50.0),
    "claude-fable-5": (10.0, 1.0, 50.0),
    "claude-opus-5-5": (4.0, 0.2, 20.0),
    "claude-opus-5": (5.0, 0.5, 25.0),
    "claude-opus-4-8": (5.0, 0.5, 25.0),
    "claude-opus-4-7": (5.0, 0.5, 25.0),
    "claude-sonnet-5": (2.0, 0.2, 10.0),
    "claude-sonnet-4-5": (3.0, 0.3, 15.0),
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
    logger.info("claude models: %d catalogue rows added, %d tariffs set", added, priced)


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
