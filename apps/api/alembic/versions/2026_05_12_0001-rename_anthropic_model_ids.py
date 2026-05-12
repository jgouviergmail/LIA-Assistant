"""Normalize Anthropic model ids: dotted ``claude-opus-4.6`` -> dashed ``claude-opus-4-6``.

The LLM catalogue (``llm_models``) and the LLM config overrides
(``llm_config_overrides``) historically stored Anthropic 4.x models with a dot
between the major and minor version (``claude-opus-4.5``, ``claude-opus-4.6``,
``claude-sonnet-4.6``, ``claude-haiku-4.5``). The Anthropic API only accepts the
dashed form (``claude-opus-4-6`` …); calling it with a dotted id returns
``404 not_found_error``. ``src/core/config/llm.py`` already uses the dashed form,
so this migration aligns the database with the real API identifiers.

Scope:
- ``llm_models.model_name``    — catalogue rows (drives the admin dropdown).
- ``llm_config_overrides.model`` — per-LLM-type model bindings.

Historical usage logs (``token_usage_logs.model_name``,
``heartbeat_notifications.model_name``) are deliberately left untouched — they
record what was actually used at the time and must not be rewritten.

Pattern matched: ``claude-<family>-<major>.<minor>`` (e.g. ``claude-opus-4.6``).
This never touches dated 3.x ids such as ``claude-3-5-sonnet-20241022`` (the
leading segment after ``claude-`` is a digit there, not ``[a-z]+``).

Downgrade restores the dotted form for the same pattern.

Revision ID: rename_anthropic_model_ids_001
Revises: tts_aggregates_001
Create Date: 2026-05-12
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "rename_anthropic_model_ids_001"
down_revision: str | None = "tts_aggregates_001"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


# Matches ``claude-<family>-<major>.<minor>`` and captures family+major / minor.
_DOTTED_RE = r"^(claude-[a-z]+-[0-9]+)\.([0-9]+)$"
# Matches ``claude-<family>-<major>-<minor>`` (the dashed canonical form).
_DASHED_RE = r"^(claude-[a-z]+-[0-9]+)-([0-9]+)$"


def _rename(column_table: str, column: str, src_re: str, sep: str) -> None:
    """Rewrite ``column`` from one separator form to the other for Claude ids."""
    op.execute(
        sa.text(
            f"UPDATE {column_table} "
            f"SET {column} = regexp_replace({column}, :src, '\\1{sep}\\2') "
            f"WHERE {column} ~ :src"
        ).bindparams(src=src_re)
    )


def upgrade() -> None:
    # llm_models: catalogue rows. Unique on model_name; the dashed targets do
    # not currently exist, so no collision. If a collision ever did exist the
    # UPDATE would abort the migration cleanly.
    _rename("llm_models", "model_name", _DOTTED_RE, "-")
    _rename("llm_config_overrides", "model", _DOTTED_RE, "-")


def downgrade() -> None:
    _rename("llm_config_overrides", "model", _DASHED_RE, ".")
    _rename("llm_models", "model_name", _DASHED_RE, ".")
