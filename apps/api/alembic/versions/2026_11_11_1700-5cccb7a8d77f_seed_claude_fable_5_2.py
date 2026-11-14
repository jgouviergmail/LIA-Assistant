"""Carry Claude Fable 5.2, released 2026-11-09, to the instances that upgrade.

Revision ID: 5cccb7a8d77f
Revises: 92fba8ef5778
Create Date: 2026-11-11 17:00:00.000000

Read on 2026-11-11 on Anthropic's own pages (the model overview, « What's new in
Claude Fable 5.2 », the effort reference and the pricing page), then measured the
same day on the Claude API: the Models API for the limits and the effort
levels, validation requests for what the model refuses. The prices are the
pricing page's.

``claude-fable-5-2`` joins the catalogue and the price table: 1M in / 128K out,
text and images in, adaptive thinking always on (``disabled`` and a budget are
400s), five effort levels with ``high`` unasked, sampling and a forced
``tool_choice`` refused, a thinking block bound to its conversation -- on every
account, whatever its age (``core/claude_surface.py``, the Fable 5.1 row). The
tariff is the list price, 8 / 0.20 / 40 USD per million tokens: the cache read is
0.025x the input, like Fable 5.1's, and the whole 1M window is billed at this
one rate.

An upgraded instance never replays the seed bundle (``APPLY_SEEDS=false`` in
production), so the row travels here, under this repository's tariff rules:

* the catalogue row is inserted only when the model is unknown (``ON CONFLICT
  (model_name) DO NOTHING``) -- a row an administrator curated stands -- and its
  provenance is ``verified``: a person read every capability on the vendor's
  pages;
* the tariff is inserted only when the model has NO active tariff, dated like
  the bundle's own row so a fresh install, where this runs first, lands on the
  same row.

A guard test holds the bundle and these values equal.
"""

from __future__ import annotations

import json
import logging
from collections.abc import Sequence
from datetime import datetime
from typing import Any, NamedTuple

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "5cccb7a8d77f"
down_revision: str | None = "92fba8ef5778"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

# print() raises UnicodeEncodeError under a CP1252 Windows console (audit F047).
logger = logging.getLogger("alembic.runtime.migration")

#: The day the vendor's pages were read, and the seed bundle's row's date.
EFFECTIVE_FROM = "2026-11-11T00:00:00+00:00"
#: The same instant as a bound value: asyncpg refuses a string for a
#: ``timestamptz`` parameter where psycopg casts it.
EFFECTIVE_FROM_AT = datetime.fromisoformat(EFFECTIVE_FROM)
PRICING_UNIT = "per_1m_tokens"
#: Read by a person on the vendor's pages (see the module docstring).
PROVENANCE = "verified"


class Tariff(NamedTuple):
    """One token tariff, USD per million tokens (``cached`` None: no cache price)."""

    input: str
    cached: str | None
    output: str


#: One entry per model, column names the seed's.
CATALOGUE_ROWS: tuple[dict[str, Any], ...] = (
    {
        "provider": "anthropic",
        "model_name": "claude-fable-5-2",
        "max_input_tokens": 1_000_000,
        "max_output_tokens": 128_000,
        "supports_tools": True,
        "supports_structured_output": True,
        "supports_strict_mode": False,
        "supports_streaming": True,
        "supports_vision": True,
        "is_reasoning_model": True,
        # « Omit temperature, top_p, and top_k »: a 400 otherwise, like every
        # Claude row from Opus 4.7 on; top_p never reaches a Claude model (the
        # adapter drops it).
        "supports_temperature": False,
        "supports_top_p": False,
        "supports_frequency_penalty": False,
        "supports_presence_penalty": False,
        "kind": "chat",
        # No ``none``: adaptive thinking cannot be switched off.
        "reasoning_enum_values": ["low", "medium", "high", "xhigh", "max"],
        "reasoning_doc_i18n_key": "anthropic_always_on",
        "is_active": True,
    },
)

#: The model's tariff -- the seed bundle's row.
TARIFFS: dict[str, Tariff] = {"claude-fable-5-2": Tariff("8", "0.20", "40")}

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

#: The model's tariff, only where it has none active; a row a downgrade retired
#: comes back rather than a second one being inserted.
INSERT_TARIFF = sa.text("""
    INSERT INTO llm_model_pricing (
        id, model_id, input_unit_price, cached_input_unit_price, output_unit_price,
        pricing_unit, effective_from, is_active, created_at, updated_at
    )
    SELECT gen_random_uuid(), m.id, CAST(:input_price AS numeric),
           CAST(:cached_price AS numeric), CAST(:output_price AS numeric),
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

#: Downgrade: retire the tariff this migration dated.
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


def tariff_params(model_name: str, tariff: Tariff) -> dict[str, Any]:
    """The bind parameters of one tariff.

    Args:
        model_name: The model the tariff prices.
        tariff: Its three prices.

    Returns:
        The parameters the tariff statements take.
    """
    return {
        "model_name": model_name,
        "input_price": tariff.input,
        "cached_price": tariff.cached,
        "output_price": tariff.output,
        "unit": PRICING_UNIT,
        "effective_from": EFFECTIVE_FROM_AT,
    }


def upgrade() -> None:
    """Add Fable 5.2 where unknown, and price it where it has no active tariff."""
    bind = op.get_bind()
    added = sum(bind.execute(INSERT_MODEL, model_params(row)).rowcount for row in CATALOGUE_ROWS)
    priced = sum(
        bind.execute(INSERT_TARIFF, tariff_params(name, tariff)).rowcount
        for name, tariff in TARIFFS.items()
    )
    logger.info("claude fable 5.2: %d catalogue rows added, %d tariffs set", added, priced)


def downgrade() -> None:
    """Retire the tariff this migration dated; the catalogue row stays.

    A catalogue row is not deleted: an administrator may have configured a slot
    on it since, and deactivating a referenced model is the trap ADR-244 names.
    """
    bind = op.get_bind()
    for name in TARIFFS:
        bind.execute(RETIRE_TARIFF, {"model_name": name, "effective_from": EFFECTIVE_FROM_AT})
