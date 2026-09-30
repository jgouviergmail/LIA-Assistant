"""Carry Claude Sonnet 5.5 and GPT-6.1 Sol, which the reference seed gained on 2026-09-30.

Revision ID: fc0147eeb095
Revises: 00c0324db6ae
Create Date: 2026-09-30 18:00:00.000000

Two chat models joined ``infrastructure/database/seeds/llm_pricing_seed.sql``
on 2026-09-30, each read on its vendor's own pages:

* ``claude-sonnet-5-5`` -- the Claude Models API (1M in, 128K out, effort
  ``low``..``max``), the pricing page (Sonnet 5's prices) and the migration
  guide: ``disabled`` is refused, so the ladder's ``none`` is rendered as
  ``between_tools``, its lowest setting (``core/claude_surface.py``);
* ``gpt-6.1-sol`` -- developers.openai.com (1 050 000-token window and 128 000
  output, so 922 000 of input like every GPT-6 row), whose ladder has no
  ``none`` (a 400, measured) and whose cached input costs 5% of the input.

An upgraded instance never replays the seed bundle (``APPLY_SEEDS=false`` in
production), so the models travel here, under the rules of ``f6c2a8e4b0d7``:

* a catalogue row is inserted only when the model is unknown (``ON CONFLICT
  (model_name) DO NOTHING``) — a row an administrator curated stands;
* a tariff is inserted only when the model has NO active tariff — a price an
  administrator set stands — and our own row, retired by a downgrade, is
  re-activated rather than duplicated;
* provenance ``verified``: every capability below was read by a person on the
  vendor's own pages, so ``get_effective_context_window`` trusts it.

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
revision: str = "fc0147eeb095"
down_revision: str | None = "00c0324db6ae"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

# print() raises UnicodeEncodeError under a CP1252 Windows console (audit F047).
logger = logging.getLogger("alembic.runtime.migration")

#: Same instant as the seed bundle, so both sources describe ONE tariff row.
EFFECTIVE_FROM = "2026-09-30T00:00:00+00:00"
#: The same instant as a bound value: asyncpg refuses a string for a
#: ``timestamptz`` parameter where psycopg casts it.
EFFECTIVE_FROM_AT = datetime.fromisoformat(EFFECTIVE_FROM)
PRICING_UNIT = "per_1m_tokens"
#: Read by a person on each vendor's pages (see the module docstring).
PROVENANCE = "verified"

#: One entry per model, column names the seed's.
CATALOGUE_ROWS: tuple[dict[str, Any], ...] = (
    {
        "provider": "anthropic",
        "model_name": "claude-sonnet-5-5",
        "max_input_tokens": 1_000_000,
        "max_output_tokens": 128_000,
        "supports_tools": True,
        "supports_structured_output": True,
        "supports_strict_mode": False,
        "supports_streaming": True,
        "supports_vision": True,
        "is_reasoning_model": True,
        # « Sampling parameters » return a 400, like every Claude row from
        # Opus 4.7 on; top_p never reaches a Claude model (the adapter drops it).
        "supports_temperature": False,
        "supports_top_p": False,
        "supports_frequency_penalty": False,
        "supports_presence_penalty": False,
        "kind": "chat",
        "reasoning_enum_values": ["none", "low", "medium", "high", "xhigh", "max"],
        "reasoning_doc_i18n_key": "anthropic_between_tools",
        "is_active": True,
    },
    {
        "provider": "openai",
        "model_name": "gpt-6.1-sol",
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
        "reasoning_enum_values": ["low", "medium", "high", "xhigh", "max"],
        "reasoning_doc_i18n_key": None,
        "is_active": True,
    },
)

#: USD per 1M tokens: (input, cached input, output) — the seed bundle's rows.
TARIFFS: dict[str, tuple[float, float | None, float]] = {
    "claude-sonnet-5-5": (2.0, 0.2, 10.0),
    "gpt-6.1-sol": (2.0, 0.1, 10.0),
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
    logger.info(
        "sonnet 5.5 and gpt-6.1-sol: %d catalogue rows added, %d tariffs set", added, priced
    )


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
