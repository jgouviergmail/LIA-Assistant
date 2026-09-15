"""Carry DeepSeek's current name into the catalogue, priced, with its documented ladder.

Revision ID: e9b5d7f3a2c4
Revises: d8a4c6e2f7b1
Create Date: 2026-09-12 15:00:00.000000

DeepSeek renamed its flagship: the API's model is ``deepseek-flash``
(DeepSeek-V4.1-Flash) and ``deepseek-v4-flash`` is a retired alias the API
still accepts. Production created the row by hand on 2026-09-11 (provenance
``verified``) — and every other upgraded instance has no row at all, because
production never replays the reference SQL seed bundle (``APPLY_SEEDS`` is a
fresh-install switch). The catalogue row and its tariff therefore travel by
migration, the way ``seed_openai_pricing`` and ``seed_meetings_stt_pricing`` do.

Three rules, all about not inventing business data (ADR-228, ADR-244):

* the catalogue row is inserted only when the model is unknown — ``ON
  CONFLICT (model_name) DO NOTHING`` — so a row an administrator curated stands;
* a tariff is inserted only when the model has NO active tariff, and when OUR
  row already exists retired the conflict re-activates it (``DO UPDATE``, never
  ``DO NOTHING``: a downgrade/upgrade cycle must not leave the model billed
  zero in silence);
* the family's declared ladders learn ``low``: the vendor documents
  ``low/high/max`` (api-docs.deepseek.com/guides/thinking_mode, read
  2026-09-12) where the rows declared ``["none", "high", "max"]``. Only a row
  declaring exactly the OLD full ladder is widened — a narrowing an
  administrator chose is theirs and stays.

The values mirror ``infrastructure/database/seeds/llm_pricing_seed.sql`` row for
row (same ``effective_from``, so the bundle's ``ON CONFLICT (model_id,
effective_from) DO UPDATE`` lands on the same row on a fresh install); a guard
test holds the two sources equal.
"""

from __future__ import annotations

import json
import logging
from collections.abc import Sequence
from typing import Any

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "e9b5d7f3a2c4"
down_revision: str | None = "d8a4c6e2f7b1"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

# print() raises UnicodeEncodeError under a CP1252 Windows console (audit F047).
logger = logging.getLogger("alembic.runtime.migration")

MODEL_NAME = "deepseek-flash"
#: The vendor's documented ladder plus the off switch — the family's ladder in
#: ``reasoning/profiles.py``; a guard test holds the two equal.
LADDER: list[str] = ["none", "low", "high", "max"]
#: The ladder the family rows declared before ``low`` was documented.
_OLD_LADDER: list[str] = ["none", "high", "max"]
#: The family, as ``reasoning/profiles.py`` declares it; a guard test holds the
#: two equal so this migration cannot widen a row the resolver would not read.
THINKING_PREFIXES: tuple[str, ...] = ("deepseek-flash", "deepseek-v4")

#: Capabilities per the vendor's model table (api-docs.deepseek.com, read
#: 2026-09-12; models.dev publishes the same limits); column names are the seed's.
CATALOGUE_ROW: dict[str, Any] = {
    "provider": "deepseek",
    "model_name": MODEL_NAME,
    "max_input_tokens": 1_000_000,
    "max_output_tokens": 384_000,
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
    "reasoning_enum_values": LADDER,
    "reasoning_doc_i18n_key": "deepseek_v4",
    "is_active": True,
}

#: ``verified``: the capabilities above were curated by a person from the
#: vendor's own model table, exactly like the row production created by hand on
#: 2026-09-11 -- so an instance born of this migration and one born of that
#: admin edit describe the model the same way. Not ``declared`` (the column
#: defaults nobody curated, which ``get_effective_context_window`` refuses to
#: trust) and not ``imported`` (corroborated by the vendored registry snapshot,
#: which does not carry ``deepseek-flash`` until the next reviewed
#: ``task llm:catalogue:fetch``). Kept out of ``CATALOGUE_ROW`` because the
#: seed bundle's INSERT carries no provenance column.
PROVENANCE = "verified"

#: Same instant as the seed bundle, so both sources describe ONE tariff row.
EFFECTIVE_FROM = "2026-09-11T22:42:59.784553+00:00"
PRICING_UNIT = "per_1m_tokens"
#: USD per 1M tokens, off-peak (the base tariff outside every window) — the
#: vendor's table read 2026-09-12; off-peak is half of peak.
OFF_PEAK: dict[str, float] = {"input": 0.15, "cached": 0.003, "output": 0.60}
#: Peak windows, 01:00-04:00 and 06:00-10:00 UTC (ADR-223's shape).
TIME_SLOTS: list[dict[str, Any]] = [
    {
        "start_utc": "01:00",
        "end_utc": "04:00",
        "input_unit_price": 0.3,
        "cached_input_unit_price": 0.006,
        "output_unit_price": 1.2,
    },
    {
        "start_utc": "06:00",
        "end_utc": "10:00",
        "input_unit_price": 0.3,
        "cached_input_unit_price": 0.006,
        "output_unit_price": 1.2,
    },
]

_INSERT_MODEL = sa.text("""
    INSERT INTO llm_models (
        provider, model_name, max_input_tokens, max_output_tokens,
        supports_tools, supports_structured_output, supports_strict_mode,
        supports_streaming, supports_vision, is_reasoning_model,
        supports_temperature, supports_top_p, supports_frequency_penalty,
        supports_presence_penalty, kind, reasoning_enum_values,
        reasoning_doc_i18n_key, is_active, capability_provenance
    ) VALUES (
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

_INSERT_TARIFF = sa.text("""
    INSERT INTO llm_model_pricing (
        id, model_id, input_unit_price, cached_input_unit_price, output_unit_price,
        pricing_unit, effective_from, is_active, time_slots, created_at, updated_at
    )
    SELECT gen_random_uuid(), m.id, :input_price, :cached_price, :output_price,
           CAST(:unit AS pricing_unit_enum), CAST(:effective_from AS timestamptz),
           true, CAST(:time_slots AS jsonb), NOW(), NOW()
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


def _widen_ladder(declared: list[str]) -> list[str]:
    """The family's old full ladder becomes its new full ladder; anything else stays.

    Args:
        declared: The row's ``reasoning_enum_values``.

    Returns:
        The ladder to store — unchanged unless the row declared exactly the
        family's pre-``low`` ladder.
    """
    return list(LADDER) if declared == _OLD_LADDER else declared


def upgrade() -> None:
    """Add the current name where unknown, price it where unpriced, teach the family ``low``."""
    bind = op.get_bind()
    params = {
        key: (json.dumps(value) if key == "reasoning_enum_values" else value)
        for key, value in CATALOGUE_ROW.items()
    }
    bind.execute(_INSERT_MODEL, {**params, "capability_provenance": PROVENANCE})
    bind.execute(
        _INSERT_TARIFF,
        {
            "model_name": MODEL_NAME,
            "input_price": OFF_PEAK["input"],
            "cached_price": OFF_PEAK["cached"],
            "output_price": OFF_PEAK["output"],
            "unit": PRICING_UNIT,
            "effective_from": EFFECTIVE_FROM,
            "time_slots": json.dumps(TIME_SLOTS),
        },
    )

    rows = bind.execute(
        sa.text(
            "SELECT id, model_name, reasoning_enum_values FROM llm_models "
            "WHERE provider = 'deepseek' AND reasoning_enum_values IS NOT NULL"
        )
    ).fetchall()
    widened = 0
    for row_id, model_name, declared in rows:
        if not str(model_name).startswith(THINKING_PREFIXES) or not isinstance(declared, list):
            continue
        ladder = _widen_ladder([str(level) for level in declared])
        if ladder == declared:
            continue
        bind.execute(
            sa.text(
                "UPDATE llm_models SET reasoning_enum_values = CAST(:value AS jsonb) "
                "WHERE id = :row_id"
            ),
            {"value": json.dumps(ladder), "row_id": row_id},
        )
        logger.info("deepseek ladder widened: %s %s -> %s", model_name, declared, ladder)
        widened += 1
    logger.info("deepseek-flash catalogue: ladders widened=%d of %d", widened, len(rows))


def downgrade() -> None:
    """Retire the tariff this migration may have added; the catalogue row and ladders stay.

    Retiring keeps history (the doctrine of the seed bundle), and a catalogue
    row without an active tariff is exactly the state the upgrade found. The
    widened ladders are not narrowed back: ``low`` is a level the API accepts,
    and removing it would guess which rows were widened here rather than by an
    administrator.
    """
    bind = op.get_bind()
    bind.execute(_RETIRE_TARIFF, {"model_name": MODEL_NAME, "effective_from": EFFECTIVE_FROM})
