"""Carry Claude Haiku 5.5 and Sonnet 5.5's cheaper cache read, both of 2026-10-07.

Revision ID: 36ecac9a51ea
Revises: e47c0a52d9f1
Create Date: 2026-10-08 12:00:00.000000

Both were read on 2026-10-08 on Anthropic's own pages (the model overview, the
migration guide, the pricing page and the release notes), not measured: no
spend on the Anthropic account.

* ``claude-haiku-5-5`` joins the catalogue and the price table: 1M in / 128K
  out, text and images in, thinking on unless ``disabled`` (accepted at
  ``high`` effort or below), five effort levels with ``medium`` unasked,
  non-default sampling refused (``core/claude_surface.py``). It is priced by
  prompt length; the tariff is its first tier, « for prompts up to 100,000
  tokens » (0.10 / 0.01 / 0.50) -- a longer prompt pays 5x, which LIA does not
  express, so above that size the real bill is higher than the recorded one.
* ``claude-sonnet-5-5``'s cache read falls from 0.20 to 0.10 USD per million
  tokens (0.05x the input price instead of 0.1x), every other price unchanged.

An upgraded instance never replays the seed bundle (``APPLY_SEEDS=false`` in
production), so both travel here, under this repository's tariff rules:

* a catalogue row is inserted only when the model is unknown (``ON CONFLICT
  (model_name) DO NOTHING``) -- a row an administrator curated stands, and its
  provenance is ``verified``: a person read every capability on the vendor's
  pages;
* a new model's tariff is inserted only when it has NO active tariff;
* a correction retires the active tariff only while it still holds the value
  LIA shipped -- a price an administrator set stands -- then inserts the
  published one, dated like the bundle's own row so a fresh install, where this
  runs first, lands on the same row.

A guard test holds the bundle and these lists equal.
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
revision: str = "36ecac9a51ea"
down_revision: str | None = "e47c0a52d9f1"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

# print() raises UnicodeEncodeError under a CP1252 Windows console (audit F047).
logger = logging.getLogger("alembic.runtime.migration")

#: The release-notes date of both changes, and the seed bundle's rows' date.
EFFECTIVE_FROM = "2026-10-07T00:00:00+00:00"
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


class Correction(NamedTuple):
    """The published price of one model and every value LIA shipped in its place."""

    model_name: str
    published: Tariff
    shipped: tuple[Tariff, ...]


#: One entry per model, column names the seed's.
CATALOGUE_ROWS: tuple[dict[str, Any], ...] = (
    {
        "provider": "anthropic",
        "model_name": "claude-haiku-5-5",
        "max_input_tokens": 1_000_000,
        "max_output_tokens": 128_000,
        "supports_tools": True,
        "supports_structured_output": True,
        "supports_strict_mode": False,
        "supports_streaming": True,
        "supports_vision": True,
        "is_reasoning_model": True,
        # A non-default temperature or top_p is a 400, like every Claude row
        # from Opus 4.7 on; top_p never reaches a Claude model (the adapter
        # drops it).
        "supports_temperature": False,
        "supports_top_p": False,
        "supports_frequency_penalty": False,
        "supports_presence_penalty": False,
        "kind": "chat",
        "reasoning_enum_values": ["none", "low", "medium", "high", "xhigh", "max"],
        "reasoning_doc_i18n_key": "anthropic_5",
        "is_active": True,
    },
)

#: The new model's tariff -- the seed bundle's row.
TARIFFS: dict[str, Tariff] = {"claude-haiku-5-5": Tariff("0.10", "0.01", "0.50")}

#: The corrected tariffs -- the seed bundle's active rows -- and what LIA shipped.
CORRECTIONS: tuple[Correction, ...] = (
    Correction("claude-sonnet-5-5", Tariff("2", "0.10", "10"), (Tariff("2", "0.2", "10"),)),
)

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

#: A new model's tariff, only where it has none active; a row a downgrade
#: retired comes back rather than a second one being inserted.
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

#: Downgrade: retire the new model's tariff this migration dated.
RETIRE_TARIFF = sa.text("""
    UPDATE llm_model_pricing p
       SET is_active = false, updated_at = NOW()
      FROM llm_models m
     WHERE m.id = p.model_id
       AND m.model_name = :model_name
       AND p.effective_from = :effective_from
       AND p.is_active
    """)

#: Retire the model's active tariff while it holds a value LIA shipped.
RETIRE_SHIPPED = sa.text("""
    UPDATE llm_model_pricing p
       SET is_active = false, updated_at = NOW()
      FROM llm_models m
     WHERE m.id = p.model_id
       AND m.model_name = :model_name
       AND p.is_active
       AND p.input_unit_price = CAST(:input_price AS numeric)
       AND p.cached_input_unit_price IS NOT DISTINCT FROM CAST(:cached_price AS numeric)
       AND p.output_unit_price = CAST(:output_price AS numeric)
    RETURNING p.model_id
    """)

#: The published tariff, active; a row a downgrade retired comes back.
INSERT_PUBLISHED = sa.text("""
    INSERT INTO llm_model_pricing (
        id, model_id, input_unit_price, cached_input_unit_price, output_unit_price,
        pricing_unit, effective_from, is_active, created_at, updated_at
    )
    VALUES (
        gen_random_uuid(), :model_id, CAST(:input_price AS numeric),
        CAST(:cached_price AS numeric), CAST(:output_price AS numeric),
        CAST(:unit AS pricing_unit_enum), :effective_from, true, NOW(), NOW()
    )
    ON CONFLICT (model_id, effective_from) DO UPDATE
       SET input_unit_price = EXCLUDED.input_unit_price,
           cached_input_unit_price = EXCLUDED.cached_input_unit_price,
           output_unit_price = EXCLUDED.output_unit_price,
           is_active = true,
           updated_at = NOW()
    """)

#: Downgrade: retire the corrected tariff this migration dated ...
RETIRE_PUBLISHED = sa.text("""
    UPDATE llm_model_pricing p
       SET is_active = false, updated_at = NOW()
      FROM llm_models m
     WHERE m.id = p.model_id
       AND m.model_name = :model_name
       AND p.effective_from = :effective_from
       AND p.is_active
    RETURNING p.model_id
    """)

#: ... and reactivate the tariff it had replaced: the most recent other row,
#: whatever its date (an administrator may have entered it the same day).
RESTORE_PREVIOUS = sa.text("""
    UPDATE llm_model_pricing p
       SET is_active = true, updated_at = NOW()
     WHERE p.id = (
           SELECT p2.id
             FROM llm_model_pricing p2
            WHERE p2.model_id = :model_id
              AND p2.effective_from <> :effective_from
            ORDER BY p2.effective_from DESC, p2.id DESC
            LIMIT 1
     )
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


def correct(bind: sa.engine.Connection, correction: Correction) -> bool:
    """Replace a shipped tariff by the published one; an administrator's stands.

    Args:
        bind: The migration's connection.
        correction: One entry of :data:`CORRECTIONS`.

    Returns:
        True when a shipped tariff was found and replaced.
    """
    for shipped in correction.shipped:
        retired = bind.execute(
            RETIRE_SHIPPED, tariff_params(correction.model_name, shipped)
        ).scalar_one_or_none()
        if retired is not None:
            bind.execute(
                INSERT_PUBLISHED,
                {**tariff_params(correction.model_name, correction.published), "model_id": retired},
            )
            return True
    return False


def upgrade() -> None:
    """Add Haiku 5.5 where unknown and price it; correct Sonnet 5.5's cache read."""
    bind = op.get_bind()
    added = sum(bind.execute(INSERT_MODEL, model_params(row)).rowcount for row in CATALOGUE_ROWS)
    priced = sum(
        bind.execute(INSERT_TARIFF, tariff_params(name, tariff)).rowcount
        for name, tariff in TARIFFS.items()
    )
    corrected = sum(correct(bind, correction) for correction in CORRECTIONS)
    logger.info(
        "haiku 5.5 and sonnet 5.5 cache read: %d catalogue rows added, %d tariffs set, "
        "%d tariffs corrected",
        added,
        priced,
        corrected,
    )


def downgrade() -> None:
    """Retire what this migration dated; the corrected model gets its previous tariff back.

    A catalogue row is not deleted: an administrator may have configured a slot
    on it since, and deactivating a referenced model is the trap ADR-244 names.
    """
    bind = op.get_bind()
    for name in TARIFFS:
        bind.execute(RETIRE_TARIFF, {"model_name": name, "effective_from": EFFECTIVE_FROM_AT})
    for correction in CORRECTIONS:
        model_id = bind.execute(
            RETIRE_PUBLISHED,
            {"model_name": correction.model_name, "effective_from": EFFECTIVE_FROM_AT},
        ).scalar_one_or_none()
        if model_id is not None:
            bind.execute(
                RESTORE_PREVIOUS, {"model_id": model_id, "effective_from": EFFECTIVE_FROM_AT}
            )
