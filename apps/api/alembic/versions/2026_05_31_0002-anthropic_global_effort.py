"""Anthropic global ``effort`` parameter (opus-4-5).

Adds a per-model "effort" capability + a per-agent override, distinct from
``reasoning_effort`` (the thinking control). On Claude Opus 4.5, ``effort``
(Anthropic ``output_config.effort``) is an INDEPENDENT global token-spend
control (text + tools + thinking), orthogonal to the manual thinking budget.
opus-4-6 / sonnet-4-6 fold effort into their adaptive ``reasoning_effort`` enum,
so they do NOT get this separate field.

Schema:
- ``llm_models.effort_values`` (JSONB, nullable): allowed effort values, or NULL
  when the model has no separate effort control. Backfilled for opus-4-5.
- ``llm_config_overrides.effort`` (VARCHAR(20), nullable): the per-agent value.

Revision ID: anthropic_global_effort_001
Revises: anthropic_thinking_config_001
Create Date: 2026-05-31
"""

from __future__ import annotations

import json
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import JSONB

# revision identifiers, used by Alembic.
revision: str = "anthropic_global_effort_001"
down_revision: str | None = "anthropic_thinking_config_001"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_OPUS_4_5_EFFORT_VALUES = ["low", "medium", "high"]


def upgrade() -> None:
    op.add_column("llm_models", sa.Column("effort_values", JSONB, nullable=True))
    op.add_column("llm_config_overrides", sa.Column("effort", sa.String(20), nullable=True))

    op.get_bind().execute(
        sa.text(
            "UPDATE llm_models SET effort_values = CAST(:vals AS jsonb) WHERE model_name = :name"
        ).bindparams(vals=json.dumps(_OPUS_4_5_EFFORT_VALUES), name="claude-opus-4-5")
    )


def downgrade() -> None:
    op.drop_column("llm_config_overrides", "effort")
    op.drop_column("llm_models", "effort_values")
