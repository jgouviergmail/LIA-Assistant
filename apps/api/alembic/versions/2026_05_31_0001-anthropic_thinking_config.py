"""Anthropic per-model reasoning (extended thinking) configuration.

Aligns the ``llm_models`` catalogue with Anthropic's real per-model thinking
API (verified 2026-05), so the admin "Configuration LLM" screen and the factory
produce a streamable, config-driven reasoning:

- claude-opus-4-6 / claude-sonnet-4-6 → ADAPTIVE thinking. ``reasoning_widget='enum'``
  with an ``"off"`` sentinel: ``["off","low","medium","high","max"]``.
- claude-opus-4-5 / claude-haiku-4-5 → MANUAL thinking. ``reasoning_widget='toggle_budget'``,
  budget bounded 1024..16384. haiku-4-5 also flips ``is_reasoning_model`` to TRUE
  (first Haiku to support extended thinking).

The seed (llm_pricing_seed.sql) carries the same values for fresh installs;
``ON CONFLICT DO NOTHING`` means it never updates EXISTING rows, hence this
data migration for already-provisioned databases (dev + prod).

Override cleanup: opus-4-5 moves from ``enum`` to ``toggle_budget``, so any
existing ``{"effort": ...}`` override for it (and any non-toggle shape on
haiku-4-5) is reset to NULL — the admin reconfigures via the UI. opus-4-6 /
sonnet-4-6 stay ``enum`` and the new value set is a superset (adds ``off``),
so their existing overrides remain valid.

Revision ID: anthropic_thinking_config_001
Revises: phase_2_cleanup_002
Create Date: 2026-05-31
"""

from __future__ import annotations

import json
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "anthropic_thinking_config_001"
down_revision: str | None = "phase_2_cleanup_002"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


# model_name -> (is_reasoning_model, widget, enum_values_or_None, budget_range_or_None, doc_key)
_NEW: dict[str, tuple[bool, str, list[str] | None, dict | None, str | None]] = {
    "claude-haiku-4-5": (
        True,
        "toggle_budget",
        None,
        {"min": 1024, "max": 16384},
        "anthropic_haiku_4_5",
    ),
    "claude-opus-4-5": (True, "toggle_budget", None, {"min": 1024, "max": 16384}, "anthropic_4_5"),
    "claude-opus-4-6": (
        True,
        "enum",
        ["off", "low", "medium", "high", "max"],
        None,
        "anthropic_4_6",
    ),
    "claude-sonnet-4-6": (
        True,
        "enum",
        ["off", "low", "medium", "high", "max"],
        None,
        "anthropic_sonnet_4_6",
    ),
}

# Previous state (for downgrade).
_OLD: dict[str, tuple[bool, str, list[str] | None, dict | None, str | None]] = {
    "claude-haiku-4-5": (False, "none", None, None, None),
    "claude-opus-4-5": (True, "enum", ["low", "medium", "high"], None, "anthropic_4_5"),
    "claude-opus-4-6": (True, "enum", ["low", "medium", "high", "max"], None, "anthropic_4_6"),
    "claude-sonnet-4-6": (True, "enum", ["low", "medium", "high"], None, "anthropic_sonnet_4_6"),
}

# Models that switch to toggle_budget — any non-toggle override shape is invalid.
_NOW_TOGGLE = ["claude-opus-4-5", "claude-haiku-4-5"]


def _apply(rows: dict[str, tuple[bool, str, list[str] | None, dict | None, str | None]]) -> None:
    bind = op.get_bind()
    for model_name, (is_reasoning, widget, enum_values, budget_range, doc_key) in rows.items():
        bind.execute(
            sa.text("""
                UPDATE llm_models SET
                    is_reasoning_model = :is_reasoning,
                    reasoning_widget = CAST(:widget AS llm_reasoning_widget_enum),
                    reasoning_enum_values = CAST(:enum_values AS jsonb),
                    reasoning_budget_range = CAST(:budget_range AS jsonb),
                    reasoning_doc_i18n_key = :doc_key
                WHERE model_name = :name
                """).bindparams(
                is_reasoning=is_reasoning,
                widget=widget,
                enum_values=json.dumps(enum_values) if enum_values is not None else None,
                budget_range=json.dumps(budget_range) if budget_range is not None else None,
                doc_key=doc_key,
                name=model_name,
            )
        )


def upgrade() -> None:
    _apply(_NEW)

    # Reset overrides whose stored shape no longer matches toggle_budget
    # (a toggle_budget value MUST carry the 'enabled' key). Admin reconfigures
    # via the UI; the runtime merge would drop these anyway.
    op.get_bind().execute(sa.text("""
            UPDATE llm_config_overrides
            SET reasoning_effort = NULL
            WHERE model = ANY(:models)
              AND reasoning_effort IS NOT NULL
              AND NOT (reasoning_effort ? 'enabled')
            """).bindparams(models=_NOW_TOGGLE))


def downgrade() -> None:
    _apply(_OLD)
    # Override cleanup is not reversed: dropped overrides cannot be reconstructed
    # (the prior values are lost). Admin reconfigures via the UI if needed.
