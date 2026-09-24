"""Image generation serves several vendors: the reference-image price, and Qwen Image 3.0.

Revision ID: a9d3f1c7e5b2
Revises: f6c2a8e4b0d7
Create Date: 2026-09-23 16:00:00.000000

ADR-305. Three changes:

* ``image_generation_pricing.cost_per_input_image_usd`` (nullable): the price of
  each reference image an edit sends, for a family that bills them per image —
  Qwen does, at the output's tier; OpenAI bills them as tokens (NULL).
* the comments of ``users.image_generation_default_quality`` / ``_size`` stop
  listing OpenAI's vocabulary: a preference is an intent mapped onto whatever
  model the administrator configured.
* ``qwen-image-3.0-pro`` and ``qwen-image-3.0`` join the catalogue (kind
  ``image``, so the image slot may name them — ADR-244's referential rule) and
  are priced: two models × six sizes (1K and 2K; square, landscape 3:2,
  portrait 2:3), Alibaba Model Studio Germany (Frankfurt) grid, deployment
  scope Global, 0.00275 USD per reference image at every tier.

Production never replays the seed bundle (measured 2026-09-23: « Skipping SQL
seeds », ``APPLY_SEEDS=false``), so the rows travel here, mirroring
``image_generation_pricing_seed.sql`` and ``llm_pricing_seed.sql`` row for row;
a guard test holds the sources equal. Nothing an administrator wrote is
overwritten: a catalogue row is added only when unknown, a price only where the
key has no active row.

The catalogue rows keep provenance ``declared``: their window and sampling
columns are the placeholders every image row carries, which no reader consults
for an image model — nobody curated them, and the row says so.
"""

from __future__ import annotations

import logging
from collections.abc import Sequence
from datetime import datetime
from typing import Any

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "a9d3f1c7e5b2"
down_revision: str | None = "f6c2a8e4b0d7"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

# print() raises UnicodeEncodeError under a CP1252 Windows console (audit F047).
logger = logging.getLogger("alembic.runtime.migration")

#: Same instant as the seed bundle, so both sources describe ONE row per key.
EFFECTIVE_FROM = "2026-09-23T00:00:00+00:00"
#: asyncpg refuses a string for a ``timestamptz`` parameter where psycopg casts it.
EFFECTIVE_FROM_AT = datetime.fromisoformat(EFFECTIVE_FROM)

INPUT_PRICE_COMMENT = (
    "Cost per reference image sent to an edit, in USD; NULL when the "
    "vendor does not bill reference images per image"
)
QUALITY_COMMENTS = (
    "Default image quality: low, medium, high.",
    "Preferred image quality; mapped onto the configured model's offer.",
)
SIZE_COMMENTS = (
    "Default image size: 1024x1024, 1536x1024, 1024x1536.",
    "Preferred image size (WIDTHxHEIGHT); mapped onto the model's offer.",
)

#: Kind ``image``; the window and sampling columns are the image rows' placeholders.
_IMAGE_ROW: dict[str, Any] = {
    "provider": "qwen",
    "max_input_tokens": 8192,
    "max_output_tokens": 4096,
    "supports_tools": False,
    "supports_structured_output": False,
    "supports_strict_mode": False,
    "supports_streaming": False,
    "supports_vision": True,
    "is_reasoning_model": False,
    "supports_temperature": False,
    "supports_top_p": False,
    "supports_frequency_penalty": False,
    "supports_presence_penalty": False,
    "kind": "image",
    "reasoning_enum_values": None,
    "reasoning_doc_i18n_key": None,
    "is_active": True,
}
CATALOGUE_ROWS: tuple[dict[str, Any], ...] = (
    {**_IMAGE_ROW, "model_name": "qwen-image-3.0"},
    {**_IMAGE_ROW, "model_name": "qwen-image-3.0-pro"},
)

QUALITY = "standard"
INPUT_IMAGE_PRICE = 0.00275
#: (size, output price per image in USD) per model — the seed bundle's rows.
TARIFFS: dict[str, tuple[tuple[str, float], ...]] = {
    "qwen-image-3.0": (
        ("1024x1024", 0.024754),
        ("1536x1024", 0.024754),
        ("1024x1536", 0.024754),
        ("2048x2048", 0.024754),
        ("2448x1632", 0.024754),
        ("1632x2448", 0.024754),
    ),
    "qwen-image-3.0-pro": (
        ("1024x1024", 0.03438),
        ("1536x1024", 0.03438),
        ("1024x1536", 0.03438),
        ("2048x2048", 0.068761),
        ("2448x1632", 0.068761),
        ("1632x2448", 0.068761),
    ),
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
        reasoning_doc_i18n_key, is_active
    ) VALUES (
        gen_random_uuid(), NOW(), NOW(),
        :provider, :model_name, :max_input_tokens, :max_output_tokens,
        :supports_tools, :supports_structured_output, :supports_strict_mode,
        :supports_streaming, :supports_vision, :is_reasoning_model,
        :supports_temperature, :supports_top_p, :supports_frequency_penalty,
        :supports_presence_penalty, CAST(:kind AS llm_model_kind_enum),
        CAST(:reasoning_enum_values AS jsonb), :reasoning_doc_i18n_key, :is_active
    )
    ON CONFLICT (model_name) DO NOTHING
    """)

#: A price is added only where the key has no ACTIVE row — a price an
#: administrator set stands — and our own row, deactivated by a downgrade, is
#: re-activated rather than duplicated. Every parameter is bound ONCE, typed, in a
#: VALUES row the guard reads back: asyncpg refuses a parameter whose type two
#: uses deduce differently (text in a select list, varchar in a comparison).
INSERT_PRICE = sa.text("""
    INSERT INTO image_generation_pricing (
        id, provider, model, quality, size, cost_per_image_usd,
        cost_per_input_image_usd, effective_from, is_active, created_at, updated_at
    )
    SELECT gen_random_uuid(), CAST(v.provider AS llm_provider_enum), v.model, v.quality,
           v.size, v.output_price, v.input_price, v.effective_from, true, NOW(), NOW()
      FROM (VALUES (
           CAST(:provider AS varchar), CAST(:model AS varchar),
           CAST(:quality AS varchar), CAST(:size AS varchar),
           CAST(:output_price AS numeric), CAST(:input_price AS numeric),
           CAST(:effective_from AS timestamptz)
      )) AS v(provider, model, quality, size, output_price, input_price, effective_from)
     WHERE NOT EXISTS (
           SELECT 1 FROM image_generation_pricing p
            WHERE p.model = v.model AND p.quality = v.quality AND p.size = v.size
              AND p.is_active
     )
    ON CONFLICT (model, quality, size, effective_from) DO UPDATE
       SET is_active = true, updated_at = NOW()
    """)

#: The previous revision serves OpenAI alone and would OFFER a Qwen row it
#: cannot run — every active one goes, an administrator's included.
DEACTIVATE_UNSERVABLE = sa.text("""
    UPDATE image_generation_pricing
       SET is_active = false, updated_at = NOW()
     WHERE provider = CAST('qwen' AS llm_provider_enum) AND is_active
    """)


#: The previous revision serves the image slot through OpenAI alone: a slot an
#: administrator set on a Qwen image model would fail every generation. It goes
#: back to the slot's default (NULL inherits it); a chat slot on Qwen is untouched.
RESET_IMAGE_SLOT = sa.text("""
    UPDATE llm_config_overrides
       SET provider = NULL, model = NULL, updated_at = NOW()
     WHERE llm_type = 'image_generation'
       AND (provider = 'qwen' OR model LIKE 'qwen-image-%')
    """)

#: The previous revision validates preferences against OpenAI's three sizes and
#: qualities and refuses to generate otherwise. A stored intent it cannot read is
#: mapped the way the new resolver would: the cheapest quality, and the 1K size
#: of the same orientation.
RESET_PREFERENCES = sa.text("""
    UPDATE users
       SET image_generation_default_quality = CASE
               WHEN image_generation_default_quality IN ('low', 'medium', 'high')
               THEN image_generation_default_quality ELSE 'low' END,
           image_generation_default_size = CASE
               WHEN image_generation_default_size IN ('1024x1024', '1536x1024', '1024x1536')
               THEN image_generation_default_size
               WHEN image_generation_default_size !~ '^[0-9]+x[0-9]+$' THEN '1024x1536'
               WHEN split_part(image_generation_default_size, 'x', 1)::int
                    > split_part(image_generation_default_size, 'x', 2)::int THEN '1536x1024'
               WHEN split_part(image_generation_default_size, 'x', 1)::int
                    < split_part(image_generation_default_size, 'x', 2)::int THEN '1024x1536'
               ELSE '1024x1024' END
     WHERE image_generation_default_quality NOT IN ('low', 'medium', 'high')
        OR image_generation_default_size NOT IN ('1024x1024', '1536x1024', '1024x1536')
    """)


def price_params(model: str, size: str, output_price: float) -> dict[str, Any]:
    """The bind parameters of one pricing row.

    Args:
        model: A key of :data:`TARIFFS`.
        size: The row's size.
        output_price: Its price per generated image.

    Returns:
        The parameters :data:`INSERT_PRICE` takes.
    """
    return {
        "provider": "qwen",
        "model": model,
        "quality": QUALITY,
        "size": size,
        "output_price": output_price,
        "input_price": INPUT_IMAGE_PRICE,
        "effective_from": EFFECTIVE_FROM_AT,
    }


def upgrade() -> None:
    """Add the column, reword the comments, add and price the Qwen image models."""
    op.add_column(
        "image_generation_pricing",
        sa.Column(
            "cost_per_input_image_usd",
            sa.Numeric(10, 6),
            nullable=True,
            comment=INPUT_PRICE_COMMENT,
        ),
    )
    op.alter_column(
        "users",
        "image_generation_default_quality",
        existing_type=sa.String(20),
        existing_nullable=False,
        existing_comment=QUALITY_COMMENTS[0],
        comment=QUALITY_COMMENTS[1],
    )
    op.alter_column(
        "users",
        "image_generation_default_size",
        existing_type=sa.String(20),
        existing_nullable=False,
        existing_comment=SIZE_COMMENTS[0],
        comment=SIZE_COMMENTS[1],
    )

    bind = op.get_bind()
    added = 0
    for row in CATALOGUE_ROWS:
        added += bind.execute(INSERT_MODEL, row).rowcount
    priced = 0
    for model, sizes in TARIFFS.items():
        for size, output_price in sizes:
            priced += bind.execute(INSERT_PRICE, price_params(model, size, output_price)).rowcount
    logger.info("qwen image models: %d catalogue rows added, %d prices set", added, priced)


def downgrade() -> None:
    """Leave nothing the previous revision would offer without serving, or refuse.

    The Qwen rows are deactivated (history kept); the catalogue rows stay — an
    administrator may have referenced them, and deactivating a referenced model
    is the trap ADR-244 names. An image slot set on a Qwen model returns to its
    default, and preferences outside OpenAI's vocabulary are mapped into it,
    since the previous revision refuses to generate otherwise.
    """
    bind = op.get_bind()
    deactivated = bind.execute(DEACTIVATE_UNSERVABLE).rowcount
    slots = bind.execute(RESET_IMAGE_SLOT).rowcount
    remapped = bind.execute(RESET_PREFERENCES).rowcount
    logger.info(
        "qwen image models: %d prices deactivated, %d image slot reset, %d preferences remapped",
        deactivated,
        slots,
        remapped,
    )
    op.alter_column(
        "users",
        "image_generation_default_size",
        existing_type=sa.String(20),
        existing_nullable=False,
        existing_comment=SIZE_COMMENTS[1],
        comment=SIZE_COMMENTS[0],
    )
    op.alter_column(
        "users",
        "image_generation_default_quality",
        existing_type=sa.String(20),
        existing_nullable=False,
        existing_comment=QUALITY_COMMENTS[1],
        comment=QUALITY_COMMENTS[0],
    )
    op.drop_column("image_generation_pricing", "cost_per_input_image_usd")
