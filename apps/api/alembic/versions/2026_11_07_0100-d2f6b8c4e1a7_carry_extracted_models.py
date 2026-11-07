"""Carry the models and the price the 2026-11-06 extraction added to the reference seeds.

Revision ID: d2f6b8c4e1a7
Revises: c8e4a1f27b53
Create Date: 2026-11-07 01:00:00.000000

The seeds were realigned on production on 2026-11-06, and an upgraded instance never replays them
(``APPLY_SEEDS=false``), so what they gained travels here, under the rules of ``f6c2a8e4b0d7``:

* ``gpt-6.1-terra`` joins the catalogue only when unknown, and is priced only when it has no active
  tariff;
* ``gpt-image-2.5-flare`` and ``gpt-image-2.6-flare`` are priced only where a quality and a size have
  no active row: their family already serves them, so a price is all they lack;
* ``drama-3`` moves from the placeholder LIA shipped to the price production reads, only while the
  active tariff is still that placeholder: an administrator's price stands.

The values mirror the seed bundle row for row, with the same ``effective_from``, so the bundle's
upsert lands on the same rows on a fresh install, where this migration runs first; a guard test
holds the two sources equal. The superseded image rows of the bundle stay out: a tariff nobody ever
paid here has no history to keep.
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
revision: str = "d2f6b8c4e1a7"
down_revision: str | None = "c8e4a1f27b53"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

# print() raises UnicodeEncodeError under a CP1252 Windows console (audit F047).
logger = logging.getLogger("alembic.runtime.migration")

PRICING_UNIT = "per_1m_tokens"
#: Read by a person on its vendor's pages on 2026-11-06.
PROVENANCE = "verified"

TERRA: dict[str, Any] = {
    "provider": "openai",
    "model_name": "gpt-6.1-terra",
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
    "reasoning_enum_values": ["none", "low", "medium", "high", "xhigh", "max"],
    "reasoning_doc_i18n_key": None,
    "is_active": True,
}
#: USD per 1M tokens: (input, cached input, output) — the seed bundle's row.
TERRA_TARIFF: tuple[float, float, float] = (1.0, 0.05, 5.0)
TERRA_EFFECTIVE_FROM = datetime.fromisoformat("2026-11-06T00:00:00+00:00")

DRAMA_MODEL = "drama-3"
#: What ``a9326a120b55`` shipped: drama-3 has no published price.
DRAMA_SHIPPED_INPUT = 10.0
#: The price production reads, per million UTF-8 bytes.
DRAMA_INPUT = 50.0
DRAMA_EFFECTIVE_FROM = datetime.fromisoformat("2026-10-31T20:13:27.469366+00:00")

#: (model, quality, size, USD per image, effective_from): the bundle's active rows.
IMAGE_PRICES: tuple[tuple[str, str, str, float, str], ...] = (
    ("gpt-image-2.5-flare", "low", "1024x1024", 0.005880, "2026-09-14T20:14:06.942981+00:00"),
    ("gpt-image-2.5-flare", "medium", "1024x1024", 0.013170, "2026-09-14T20:14:31.802063+00:00"),
    ("gpt-image-2.5-flare", "high", "1024x1024", 0.052000, "2026-09-14T20:15:08.031681+00:00"),
    ("gpt-image-2.5-flare", "low", "1024x1536", 0.004740, "2026-09-14T20:15:38.104886+00:00"),
    ("gpt-image-2.5-flare", "medium", "1024x1536", 0.010290, "2026-09-14T20:15:56.850833+00:00"),
    ("gpt-image-2.5-flare", "high", "1024x1536", 0.041160, "2026-09-14T20:16:16.330217+00:00"),
    ("gpt-image-2.5-flare", "low", "1536x1024", 0.004700, "2026-09-14T20:16:51.619868+00:00"),
    ("gpt-image-2.5-flare", "medium", "1536x1024", 0.010300, "2026-09-14T20:17:08.713892+00:00"),
    ("gpt-image-2.5-flare", "high", "1536x1024", 0.041200, "2026-09-14T20:17:21.029995+00:00"),
    ("gpt-image-2.6-flare", "low", "1024x1024", 0.024690, "2026-11-06T00:00:00+00:00"),
    ("gpt-image-2.6-flare", "low", "1024x1536", 0.019920, "2026-11-06T00:00:00+00:00"),
    ("gpt-image-2.6-flare", "low", "1536x1024", 0.019920, "2026-11-06T00:00:00+00:00"),
    ("gpt-image-2.6-flare", "medium", "1024x1024", 0.043470, "2026-11-06T00:00:00+00:00"),
    ("gpt-image-2.6-flare", "medium", "1024x1536", 0.033960, "2026-11-06T00:00:00+00:00"),
    ("gpt-image-2.6-flare", "medium", "1536x1024", 0.033960, "2026-11-06T00:00:00+00:00"),
    ("gpt-image-2.6-flare", "high", "1024x1024", 0.052680, "2026-11-06T00:00:00+00:00"),
    ("gpt-image-2.6-flare", "high", "1024x1536", 0.041160, "2026-11-06T00:00:00+00:00"),
    ("gpt-image-2.6-flare", "high", "1536x1024", 0.041160, "2026-11-06T00:00:00+00:00"),
)

#: ``id`` and the timestamps are written explicitly: the ORM declares only client-side defaults
#: for them, so a schema built from the models (the integration tests') has no server default.
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
           CAST(:unit AS pricing_unit_enum), :effective_from, true, NOW(), NOW()
      FROM llm_models m
     WHERE m.model_name = :model_name
       AND NOT EXISTS (
           SELECT 1 FROM llm_model_pricing p WHERE p.model_id = m.id AND p.is_active
       )
    ON CONFLICT (model_id, effective_from) DO UPDATE
       SET is_active = true, updated_at = NOW()
    """)

#: Only the placeholder goes: any other price is an administrator's.
RETIRE_PLACEHOLDER = sa.text("""
    UPDATE llm_model_pricing p
       SET is_active = false, updated_at = NOW()
      FROM llm_models m
     WHERE m.id = p.model_id
       AND m.model_name = :model_name
       AND p.is_active
       AND p.input_unit_price = :shipped
    """)

#: Every value carries its type: asyncpg reads a parameter once per statement (ADR-305).
INSERT_IMAGE_PRICE = sa.text("""
    INSERT INTO image_generation_pricing (
        id, provider, model, quality, size, cost_per_image_usd,
        cost_per_input_image_usd, effective_from, is_active, created_at, updated_at
    )
    SELECT gen_random_uuid(), CAST('openai' AS llm_provider_enum), v.model, v.quality,
           v.size, v.price, NULL, v.effective_from, true, NOW(), NOW()
      FROM (VALUES (
           CAST(:model AS varchar), CAST(:quality AS varchar), CAST(:size AS varchar),
           CAST(:price AS numeric), CAST(:effective_from AS timestamptz)
      )) AS v(model, quality, size, price, effective_from)
     WHERE NOT EXISTS (
           SELECT 1 FROM image_generation_pricing p
            WHERE p.model = v.model AND p.quality = v.quality AND p.size = v.size
              AND p.is_active
     )
    ON CONFLICT (model, quality, size, effective_from) DO UPDATE
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

RETIRE_IMAGE_PRICE = sa.text("""
    UPDATE image_generation_pricing
       SET is_active = false, updated_at = NOW()
     WHERE model = CAST(:model AS varchar)
       AND quality = CAST(:quality AS varchar)
       AND size = CAST(:size AS varchar)
       AND effective_from = CAST(:effective_from AS timestamptz)
       AND is_active
    """)


def terra_params() -> dict[str, Any]:
    """The bind parameters of the catalogue row."""
    return {
        **TERRA,
        "reasoning_enum_values": json.dumps(TERRA["reasoning_enum_values"]),
        "capability_provenance": PROVENANCE,
    }


def terra_tariff_params() -> dict[str, Any]:
    """The bind parameters of its tariff."""
    input_price, cached_price, output_price = TERRA_TARIFF
    return {
        "model_name": TERRA["model_name"],
        "input_price": input_price,
        "cached_price": cached_price,
        "output_price": output_price,
        "unit": PRICING_UNIT,
        "effective_from": TERRA_EFFECTIVE_FROM,
    }


def drama_tariff_params() -> dict[str, Any]:
    """The bind parameters of the price that replaces the placeholder."""
    return {
        "model_name": DRAMA_MODEL,
        "input_price": DRAMA_INPUT,
        "cached_price": None,
        "output_price": 0.0,
        "unit": PRICING_UNIT,
        "effective_from": DRAMA_EFFECTIVE_FROM,
    }


def image_params(row: tuple[str, str, str, float, str]) -> dict[str, Any]:
    """The bind parameters of one image price.

    Args:
        row: An entry of :data:`IMAGE_PRICES`.

    Returns:
        The parameters :data:`INSERT_IMAGE_PRICE` takes.
    """
    model, quality, size, price, effective_from = row
    return {
        "model": model,
        "quality": quality,
        "size": size,
        "price": price,
        "effective_from": datetime.fromisoformat(effective_from),
    }


def upgrade() -> None:
    """Add what an instance lacks, and leave whatever an administrator set."""
    bind = op.get_bind()
    added = bind.execute(INSERT_MODEL, terra_params()).rowcount
    priced = bind.execute(INSERT_TARIFF, terra_tariff_params()).rowcount
    bind.execute(RETIRE_PLACEHOLDER, {"model_name": DRAMA_MODEL, "shipped": DRAMA_SHIPPED_INPUT})
    corrected = bind.execute(INSERT_TARIFF, drama_tariff_params()).rowcount
    images = sum(
        bind.execute(INSERT_IMAGE_PRICE, image_params(row)).rowcount for row in IMAGE_PRICES
    )
    logger.info(
        "extracted models: %d catalogue row, %d tariff, %d correction, %d image prices",
        added,
        priced,
        corrected,
        images,
    )


def downgrade() -> None:
    """Retire the prices this revision may have added; the catalogue row and drama-3's stay.

    Retiring keeps history, and a catalogue row is never deleted: an administrator may have set a
    slot on it. The placeholder is not restored: it was never a price.
    """
    bind = op.get_bind()
    bind.execute(
        RETIRE_TARIFF,
        {"model_name": TERRA["model_name"], "effective_from": TERRA_EFFECTIVE_FROM},
    )
    for row in IMAGE_PRICES:
        params = image_params(row)
        del params["price"]
        bind.execute(RETIRE_IMAGE_PRICE, params)
