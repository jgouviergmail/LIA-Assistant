"""Correct every price the 2026-09-23 audit found different from the vendor's.

Revision ID: d5f8b2a6c9e3
Revises: c3e7a1f5d9b2
Create Date: 2026-09-23 20:00:00.000000

The audit read each vendor's pricing page against the tariffs LIA ships. Eleven
token tariffs were wrong:

* ``gpt-5.6-sol`` carried ``gpt-5.5``'s price (5 / 30 where OpenAI bills 4 / 20);
* ``deepseek-v4-flash`` is a retired name DeepSeek now serves with
  DeepSeek-V4.1-Flash « and bills at the Flash price », which LIA billed half
  again as high;
* ``gemini-3.7-flash`` carried its BATCH price and ``gemini-3.6-flash`` the price
  Google applies from 2027-01-01 -- both bill 0.75 / 3.75 until 2026-12-31;
* the two Gemini speech models carried a text model's price, where they bill
  text in and AUDIO out (0.50 / 10.00 and 1.00 / 20.00);
* five Qwen cache rates were far from Alibaba's rule for the model's cache mode
  on the Frankfurt Global scope: 20 % of the input price for an implicit hit
  (``qwen3.7-plus``, ``qwen3-max``), 10 % for an explicit hit on the three models
  the implicit cache does not cover there (``qwen3.5-flash``, ``qwen3.5-plus``,
  ``qwen3.6-plus`` -- measured: no cached token on two identical requests).

And ``gpt-image-2``'s nine per-image prices were a copy of ``gpt-image-1``'s,
where OpenAI's image guide publishes its own (0.006 to 0.211). On the Maps
Platform side, Static Street View costs $7 per 1000, not $2, and the Routes API
bills three SKU tiers: the client now files a call under the tier its request
triggers -- LIA's default drive route asks for traffic-aware routing AND tolls,
the Enterprise tier at $15 -- so the Pro and Enterprise rows are added, and the
matrix is billed per element returned.

An upgraded instance never replays the seed bundle, so the corrections travel
here -- and they correct only what LIA itself shipped. A row is retired only
while it still holds one of the values the bundle distributed (``shipped``);
a price an administrator set stands, as every tariff migration of this
repository has it. The published price is then inserted in its place, dated
like the bundle's own row so a fresh install, where this runs first, lands on
the same row. A guard test holds the bundle and this list equal.
"""

from __future__ import annotations

import json
import logging
from collections.abc import Sequence
from datetime import datetime
from decimal import Decimal
from typing import Any, NamedTuple

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "d5f8b2a6c9e3"
down_revision: str | None = "c3e7a1f5d9b2"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

# print() raises UnicodeEncodeError under a CP1252 Windows console (audit F047).
logger = logging.getLogger("alembic.runtime.migration")

#: Same instant as the seed bundle's corrected rows.
EFFECTIVE_FROM = "2026-09-23T00:00:00+00:00"
#: The same instant as a bound value: asyncpg refuses a string for a
#: ``timestamptz`` parameter where psycopg casts it.
EFFECTIVE_FROM_AT = datetime.fromisoformat(EFFECTIVE_FROM)
PRICING_UNIT = "per_1m_tokens"


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
    time_slots: list[dict[str, Any]] | None = None


#: DeepSeek's peak windows at the Flash price (off-peak is the base price).
_FLASH_PEAK = {"input_unit_price": 0.3, "cached_input_unit_price": 0.006, "output_unit_price": 1.2}
_WEEKDAYS = [1, 2, 3, 4, 5]

CORRECTIONS: tuple[Correction, ...] = (
    Correction("gpt-5.6-sol", Tariff("4", "0.4", "20"), (Tariff("5", "0.5", "30"),)),
    Correction(
        "deepseek-v4-flash",
        Tariff("0.15", "0.003", "0.6"),
        # The windowed base, the flat peak the bundle shipped before its
        # windows, and the launch price a never-updated instance still holds.
        (
            Tariff("0.22", "0.007", "0.66"),
            Tariff("0.44", "0.014", "1.32"),
            Tariff("0.14", "0.028", "0.28"),
        ),
        time_slots=[
            {"start_utc": "01:00", "end_utc": "04:00", **_FLASH_PEAK, "weekdays": _WEEKDAYS},
            {"start_utc": "06:00", "end_utc": "10:00", **_FLASH_PEAK, "weekdays": _WEEKDAYS},
        ],
    ),
    Correction(
        "gemini-3.7-flash", Tariff("0.75", "0.075", "3.75"), (Tariff("0.375", "0.0375", "1.875"),)
    ),
    Correction(
        "gemini-3.6-flash", Tariff("0.75", "0.075", "3.75"), (Tariff("1.5", "0.15", "7.5"),)
    ),
    Correction(
        "gemini-2.5-flash-preview-tts", Tariff("0.5", None, "10"), (Tariff("0.3", "0.03", "2.5"),)
    ),
    Correction(
        "gemini-2.5-pro-preview-tts", Tariff("1", None, "20"), (Tariff("1.25", "0.125", "10"),)
    ),
    Correction(
        "qwen3.5-flash", Tariff("0.029", "0.0029", "0.287"), (Tariff("0.029", "0.02", "0.287"),)
    ),
    Correction(
        "qwen3.5-plus", Tariff("0.115", "0.0115", "0.688"), (Tariff("0.115", "0.075", "0.688"),)
    ),
    Correction(
        "qwen3.6-plus", Tariff("0.276", "0.0276", "1.651"), (Tariff("0.276", "0.18", "1.651"),)
    ),
    Correction(
        "qwen3.7-plus", Tariff("0.276", "0.0552", "1.101"), (Tariff("0.276", "0.056", "1.101"),)
    ),
    Correction(
        "qwen3-max", Tariff("0.359", "0.0718", "1.434"), (Tariff("0.359", "0.24", "1.434"),)
    ),
)

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
        pricing_unit, time_slots, effective_from, is_active, created_at, updated_at
    )
    VALUES (
        gen_random_uuid(), :model_id, CAST(:input_price AS numeric),
        CAST(:cached_price AS numeric), CAST(:output_price AS numeric),
        CAST(:unit AS pricing_unit_enum), CAST(:time_slots AS jsonb), :effective_from,
        true, NOW(), NOW()
    )
    ON CONFLICT (model_id, effective_from) DO UPDATE
       SET input_unit_price = EXCLUDED.input_unit_price,
           cached_input_unit_price = EXCLUDED.cached_input_unit_price,
           output_unit_price = EXCLUDED.output_unit_price,
           time_slots = EXCLUDED.time_slots,
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


class ImageCorrection(NamedTuple):
    """The published price of one gpt-image-2 (quality, size) and the value shipped."""

    quality: str
    size: str
    published: str
    shipped: str


#: The model whose per-image prices were a copy of gpt-image-1's.
IMAGE_MODEL = "gpt-image-2"
#: developers.openai.com/api/docs/guides/image-generation, output cost table
#: (read 2026-09-23); ``shipped`` is gpt-image-1's price for the same key.
IMAGE_CORRECTIONS: tuple[ImageCorrection, ...] = (
    ImageCorrection("low", "1024x1024", "0.006", "0.011"),
    ImageCorrection("low", "1024x1536", "0.005", "0.016"),
    ImageCorrection("low", "1536x1024", "0.005", "0.016"),
    ImageCorrection("medium", "1024x1024", "0.053", "0.042"),
    ImageCorrection("medium", "1024x1536", "0.041", "0.063"),
    ImageCorrection("medium", "1536x1024", "0.041", "0.063"),
    ImageCorrection("high", "1024x1024", "0.211", "0.167"),
    ImageCorrection("high", "1024x1536", "0.165", "0.25"),
    ImageCorrection("high", "1536x1024", "0.165", "0.25"),
)

#: Retire the active price of one key while it holds the value LIA shipped.
RETIRE_SHIPPED_IMAGE = sa.text("""
    UPDATE image_generation_pricing
       SET is_active = false, updated_at = NOW()
     WHERE model = :model AND quality = :quality AND size = :size
       AND is_active
       AND cost_per_image_usd = CAST(:price AS numeric)
       AND cost_per_input_image_usd IS NULL
    RETURNING provider
    """)

#: The published price, active; a row a downgrade retired comes back. Every
#: parameter is bound once, typed (asyncpg deduces one type per parameter).
INSERT_PUBLISHED_IMAGE = sa.text("""
    INSERT INTO image_generation_pricing (
        id, provider, model, quality, size, cost_per_image_usd,
        cost_per_input_image_usd, effective_from, is_active, created_at, updated_at
    )
    VALUES (
        gen_random_uuid(), CAST(:provider AS llm_provider_enum), CAST(:model AS varchar),
        CAST(:quality AS varchar), CAST(:size AS varchar), CAST(:price AS numeric),
        NULL, :effective_from, true, NOW(), NOW()
    )
    ON CONFLICT (model, quality, size, effective_from) DO UPDATE
       SET cost_per_image_usd = EXCLUDED.cost_per_image_usd,
           is_active = true,
           updated_at = NOW()
    """)

#: Downgrade: retire the corrected price this migration dated ...
RETIRE_PUBLISHED_IMAGE = sa.text("""
    UPDATE image_generation_pricing
       SET is_active = false, updated_at = NOW()
     WHERE model = :model AND quality = :quality AND size = :size
       AND effective_from = :effective_from
       AND is_active
    RETURNING id
    """)

#: ... and reactivate the most recent other price of the same key.
RESTORE_PREVIOUS_IMAGE = sa.text("""
    UPDATE image_generation_pricing
       SET is_active = true, updated_at = NOW()
     WHERE id = (
           SELECT p.id
             FROM image_generation_pricing p
            WHERE p.model = :model AND p.quality = :quality AND p.size = :size
              AND p.effective_from <> :effective_from
            ORDER BY p.effective_from DESC, p.id DESC
            LIMIT 1
     )
    """)


class GooglePrice(NamedTuple):
    """One Maps Platform price, USD per 1000 billable events.

    ``shipped`` / ``shipped_sku`` name the row an instance holds when it is a
    correction; both are None for a row this migration adds.
    """

    api_name: str
    endpoint: str
    sku_name: str
    price: str
    shipped: str | None = None
    shipped_sku: str | None = None


#: developers.google.com/maps/billing-and-pricing/pricing (read 2026-09-23).
#: The Routes client files each call under the SKU its request triggers
#: (``routes_sku_suffix``); the Route Matrix is billed per element returned.
GOOGLE_PRICES: tuple[GooglePrice, ...] = (
    GooglePrice("street_view", "/streetview", "Street View Static", "7", "2", "Street View Static"),
    GooglePrice(
        "routes",
        "/directions/v2:computeRoutes",
        "Compute Routes Essentials",
        "5",
        "5",
        "Compute Routes",
    ),
    GooglePrice("routes", "/directions/v2:computeRoutes:pro", "Compute Routes Pro", "10"),
    GooglePrice(
        "routes", "/directions/v2:computeRoutes:enterprise", "Compute Routes Enterprise", "15"
    ),
    GooglePrice(
        "routes",
        "/distanceMatrix/v2:computeRouteMatrix",
        "Compute Route Matrix Essentials",
        "5",
        "5",
        "Route Matrix",
    ),
    GooglePrice(
        "routes", "/distanceMatrix/v2:computeRouteMatrix:pro", "Compute Route Matrix Pro", "10"
    ),
    GooglePrice(
        "routes",
        "/distanceMatrix/v2:computeRouteMatrix:enterprise",
        "Compute Route Matrix Enterprise",
        "15",
    ),
)

#: Correct a row in place while it holds the value LIA shipped (the table keeps
#: no price history: every call's cost is stored with the call).
CORRECT_GOOGLE = sa.text("""
    UPDATE google_api_pricing
       SET cost_per_1000_usd = CAST(:price AS numeric),
           sku_name = CAST(:sku_name AS varchar),
           updated_at = NOW()
     WHERE api_name = CAST(:api_name AS varchar)
       AND endpoint = CAST(:endpoint AS varchar)
       AND is_active
       AND cost_per_1000_usd = CAST(:shipped AS numeric)
       AND sku_name = CAST(:shipped_sku AS varchar)
    """)

#: Add a price where the endpoint has no active row.
INSERT_GOOGLE = sa.text("""
    INSERT INTO google_api_pricing (
        id, api_name, endpoint, sku_name, cost_per_1000_usd, effective_from,
        is_active, created_at, updated_at
    )
    SELECT gen_random_uuid(), v.api_name, v.endpoint, v.sku_name, v.price,
           v.effective_from, true, NOW(), NOW()
      FROM (VALUES (
           CAST(:api_name AS varchar), CAST(:endpoint AS varchar),
           CAST(:sku_name AS varchar), CAST(:price AS numeric),
           CAST(:effective_from AS timestamptz)
      )) AS v(api_name, endpoint, sku_name, price, effective_from)
     WHERE NOT EXISTS (
           SELECT 1 FROM google_api_pricing p
            WHERE p.api_name = v.api_name AND p.endpoint = v.endpoint AND p.is_active
     )
    """)

#: Downgrade: remove a row this migration added (dated like the audit).
DELETE_GOOGLE = sa.text("""
    DELETE FROM google_api_pricing
     WHERE api_name = CAST(:api_name AS varchar)
       AND endpoint = CAST(:endpoint AS varchar)
       AND effective_from = CAST(:effective_from AS timestamptz)
    """)


def google_params(row: GooglePrice) -> dict[str, Any]:
    """Bind parameters of one Maps Platform price."""
    return {
        "api_name": row.api_name,
        "endpoint": row.endpoint,
        "sku_name": row.sku_name,
        "price": Decimal(row.price),
    }


def image_key(correction: ImageCorrection) -> dict[str, Any]:
    """The bind parameters naming one price key."""
    return {"model": IMAGE_MODEL, "quality": correction.quality, "size": correction.size}


def tariff_params(model_name: str, tariff: Tariff) -> dict[str, Any]:
    """Bind parameters matching ``tariff`` (numerics as ``Decimal``, asyncpg-safe)."""
    return {
        "model_name": model_name,
        "input_price": Decimal(tariff.input),
        "cached_price": None if tariff.cached is None else Decimal(tariff.cached),
        "output_price": Decimal(tariff.output),
    }


def published_params(model_id: Any, correction: Correction) -> dict[str, Any]:
    """Bind parameters of the published row of ``correction`` for one model id."""
    return {
        **tariff_params(correction.model_name, correction.published),
        "model_id": model_id,
        "unit": PRICING_UNIT,
        "time_slots": None if correction.time_slots is None else json.dumps(correction.time_slots),
        "effective_from": EFFECTIVE_FROM_AT,
    }


def upgrade() -> None:
    """Replace each shipped value still active by the published price."""
    bind = op.get_bind()
    corrected = 0
    for correction in CORRECTIONS:
        for shipped in correction.shipped:
            for (model_id,) in bind.execute(
                RETIRE_SHIPPED, tariff_params(correction.model_name, shipped)
            ).all():
                bind.execute(INSERT_PUBLISHED, published_params(model_id, correction))
                corrected += 1
    images = 0
    for image in IMAGE_CORRECTIONS:
        for (provider,) in bind.execute(
            RETIRE_SHIPPED_IMAGE, {**image_key(image), "price": Decimal(image.shipped)}
        ).all():
            bind.execute(
                INSERT_PUBLISHED_IMAGE,
                {
                    **image_key(image),
                    "provider": provider,
                    "price": Decimal(image.published),
                    "effective_from": EFFECTIVE_FROM_AT,
                },
            )
            images += 1
    maps = 0
    for row in GOOGLE_PRICES:
        if row.shipped is None:
            statement, params = INSERT_GOOGLE, {
                **google_params(row),
                "effective_from": EFFECTIVE_FROM_AT,
            }
        else:
            statement, params = CORRECT_GOOGLE, {
                **google_params(row),
                "shipped": Decimal(row.shipped),
                "shipped_sku": row.shipped_sku,
            }
        maps += bind.execute(statement, params).rowcount
    logger.info(
        "published price corrections: %d token tariffs, %d image prices, %d Maps prices",
        corrected,
        images,
        maps,
    )


def downgrade() -> None:
    """Retire the corrected prices and reactivate the ones they replaced."""
    bind = op.get_bind()
    for correction in CORRECTIONS:
        for (model_id,) in bind.execute(
            RETIRE_PUBLISHED,
            {"model_name": correction.model_name, "effective_from": EFFECTIVE_FROM_AT},
        ).all():
            bind.execute(
                RESTORE_PREVIOUS, {"model_id": model_id, "effective_from": EFFECTIVE_FROM_AT}
            )
    for image in IMAGE_CORRECTIONS:
        key = {**image_key(image), "effective_from": EFFECTIVE_FROM_AT}
        if bind.execute(RETIRE_PUBLISHED_IMAGE, key).all():
            bind.execute(RESTORE_PREVIOUS_IMAGE, key)
    for row in GOOGLE_PRICES:
        if row.shipped is None:
            bind.execute(
                DELETE_GOOGLE,
                {
                    "api_name": row.api_name,
                    "endpoint": row.endpoint,
                    "effective_from": EFFECTIVE_FROM_AT,
                },
            )
        else:
            # The correction, reversed: back to the value that was shipped.
            bind.execute(
                CORRECT_GOOGLE,
                {
                    "api_name": row.api_name,
                    "endpoint": row.endpoint,
                    "sku_name": row.shipped_sku,
                    "price": Decimal(row.shipped),
                    "shipped": Decimal(row.price),
                    "shipped_sku": row.sku_name,
                },
            )
