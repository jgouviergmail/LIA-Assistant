"""Give the model the image slot names its catalogue row.

Revision ID: 45cf916cc02f
Revises: 43891b5db14c
Create Date: 2026-11-11 20:00:00.000000

The reference configuration seed is the production configuration, and its
``image_generation`` slot names ``gpt-image-2.6-flare``. The model is priced
(``image_generation_pricing``, carried to upgraded instances by ``d2f6b8c4e1a7``)
and served by its image family, but no door ever wrote its ``llm_models`` row:
a slot naming a model the catalogue does not carry resolves to the conservative
default profile, and the reference bundle's own verification refuses it. That
is the defect ``b1c2d3e4f5a6`` closed for ``gpt-image-2`` (ADR-244); a newer
image model reopened it, on production as on a fresh install.

The row is inserted only where the model is unknown (``ON CONFLICT (model_name)
DO NOTHING``): one an administrator holds stands. Its token limits and sampling
flags are the placeholders no reader consults for an image model -- what the
model accepts is declared by its family (``image_generation/families.py``) --
so the provenance stays ``declared``. The values mirror the seed bundle's row;
a guard test holds the two equal.
"""

from __future__ import annotations

import logging
from collections.abc import Sequence
from typing import Any

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "45cf916cc02f"
down_revision: str | None = "43891b5db14c"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

# print() raises UnicodeEncodeError under a CP1252 Windows console (audit F047).
logger = logging.getLogger("alembic.runtime.migration")

#: Nobody curated the placeholders below: see the module docstring.
PROVENANCE = "declared"

#: Column names the seed's, values the seed's row -- the shape of ``gpt-image-2``.
CATALOGUE_ROW: dict[str, Any] = {
    "provider": "openai",
    "model_name": "gpt-image-2.6-flare",
    "max_input_tokens": 8192,
    "max_output_tokens": 4096,
    "supports_tools": False,
    "supports_structured_output": True,
    "supports_strict_mode": False,
    "supports_streaming": True,
    "supports_vision": True,
    "is_reasoning_model": False,
    "supports_temperature": True,
    "supports_top_p": True,
    "supports_frequency_penalty": True,
    "supports_presence_penalty": True,
    "kind": "image",
    "reasoning_enum_values": None,
    "reasoning_doc_i18n_key": None,
    "is_active": True,
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


def model_params() -> dict[str, Any]:
    """The bind parameters of the catalogue row."""
    return {**CATALOGUE_ROW, "capability_provenance": PROVENANCE}


def upgrade() -> None:
    """Insert the row where the catalogue does not know the model."""
    added = op.get_bind().execute(INSERT_MODEL, model_params()).rowcount
    logger.info("image slot model: %d catalogue row added", added)


def downgrade() -> None:
    """The row stays.

    A slot may name it: removing it would recreate the orphan this revision
    exists to close.
    """
