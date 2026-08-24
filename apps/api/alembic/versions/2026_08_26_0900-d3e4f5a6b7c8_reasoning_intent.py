"""Rewrite stored reasoning_effort as a single intent (ADR-245, Lot 0c).

Every stored shape becomes ``{"level": ..., "budget_tokens": ...,
"exclude_from_output": ...}``. Simulated against the real data before this
migration was written: 36 override rows, 29 code defaults and 1 290
(model x stored shape) combinations, **0 divergences** in the provider kwargs
they produce. The rewrite collapses what the old shapes said three ways:

    x21  {"effort": "off"}   ->  {"level": "none"}
    x8   {"effort": "none"}  ->  {"level": "none"}
    x6   {"effort": "high"}  ->  {"level": "high"}
    x1   {"effort": "low"}   ->  {"level": "low"}

``llm_config_overrides.effort`` and ``llm_models.effort_values`` are dropped:
they fed a second channel to the same Anthropic kwarg as ``reasoning_effort``,
and ``additional_kwargs.update()`` decided which one silently won. Measured at
removal: no configured slot set it.

**This migration is not a flag day.** ``LLMAgentConfig`` and
``LLMTypeConfigUpdate`` both read the legacy shapes through
``intent_from_legacy``, so an instance that takes the code before running this
keeps working, and one that runs this before deploying the code keeps working
too. The mapper is shared with the golden-equivalence test, so the migration
and the proof cannot disagree about what a stored value meant.

Revision ID: d3e4f5a6b7c8
Revises: c2d3e4f5a6b7
Create Date: 2026-08-26 09:00:00.000000
"""

import json
import logging
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "d3e4f5a6b7c8"
down_revision: str | None = "c2d3e4f5a6b7"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

# print() raises UnicodeEncodeError under a CP1252 Windows console (audit F047).
logger = logging.getLogger("alembic.runtime.migration")


def upgrade() -> None:
    """Rewrite every stored value and drop the duplicate effort channel."""
    from dataclasses import asdict

    from src.core.reasoning_intent import intent_from_legacy, is_intent_shape

    bind = op.get_bind()
    rows = bind.execute(
        sa.text(
            "SELECT id, reasoning_effort FROM llm_config_overrides "
            "WHERE reasoning_effort IS NOT NULL"
        )
    ).fetchall()

    rewritten = already = 0
    for row_id, stored in rows:
        if not isinstance(stored, dict):
            continue
        if is_intent_shape(stored):
            already += 1
            continue
        intent = intent_from_legacy(stored)
        bind.execute(
            sa.text(
                "UPDATE llm_config_overrides SET reasoning_effort = CAST(:value AS jsonb) "
                "WHERE id = :row_id"
            ),
            {"value": json.dumps(asdict(intent)), "row_id": row_id},
        )
        rewritten += 1

    op.drop_column("llm_config_overrides", "effort")
    op.drop_column("llm_models", "effort_values")

    # The column comment is part of the schema here (audit F042: comments are
    # reconciled against the models, not tolerated), so the migration that
    # changes what the column HOLDS must also change what it SAYS -- otherwise
    # a from-scratch database differs from the ORM and the replay gate reds.
    op.alter_column(
        "llm_config_overrides",
        "reasoning_effort",
        existing_type=postgresql.JSONB(astext_type=sa.Text()),
        existing_nullable=True,
        comment=(
            "Reasoning override stored as JSONB, one shape for every provider "
            '(ADR-245): {"level": "<str>", "budget_tokens": <int|null>, '
            '"exclude_from_output": <bool>}. '
            "NULL = no override (use LLM_DEFAULTS or the model default)."
        ),
    )
    logger.info(
        "reasoning intent migration: rewritten=%d already_migrated=%d rows=%d",
        rewritten,
        already,
        len(rows),
    )


def downgrade() -> None:
    """Restore the two columns; the legacy shapes are NOT reconstructed.

    An intent does not record which of the four encodings it came from --
    ``{"effort": "off"}``, ``{"effort": "none"}`` and ``{"enabled": false}``
    all said ``level="none"`` -- so guessing one would write a shape the old
    builders might reject. The stored intents are left in place instead: the
    pre-ADR-245 code refuses them at read time, which is a loud, immediate
    failure rather than a silent wrong reasoning mode.

    The two columns come back empty, which is what they were on every slot.
    """
    op.add_column(
        "llm_models",
        sa.Column(
            "effort_values",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=True,
            comment=(
                "Allowed values for a separate global 'effort' control (Anthropic "
                "output_config.effort), distinct from reasoning_effort. NULL = the "
                "model has no separate effort field. Currently only claude-opus-4-5."
            ),
        ),
    )
    op.add_column(
        "llm_config_overrides",
        sa.Column("effort", sa.String(length=32), nullable=True),
    )
    op.alter_column(
        "llm_config_overrides",
        "reasoning_effort",
        existing_type=postgresql.JSONB(astext_type=sa.Text()),
        existing_nullable=True,
        comment=(
            "Reasoning effort override stored as JSONB. Discriminated by the "
            "associated model's reasoning_widget: "
            '{"effort": "<str>"} for widget=enum, '
            '{"budget": <int>} for widget=budget_int, '
            '{"enabled": <bool>, "budget": <int|null>} for widget=toggle_budget. '
            "NULL = no override (use LLM_DEFAULTS or model default)."
        ),
    )
