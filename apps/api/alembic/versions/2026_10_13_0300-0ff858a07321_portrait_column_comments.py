"""Align the portrait column comments with what the columns hold since ADR-343.

Revision ID: 0ff858a07321
Revises: 1bd74bd9a0cf
Create Date: 2026-10-13 03:00:00.000000

ADR-343 grew the portrait's sources from four to nine and made each format a
set of its own claims under token TARGETS rather than the fixed ~200/~60-token
sizes the comments still stated. Column comments are part of the schema
contract (audit F042): the model now declares the new wording, so the schema
must carry it too.
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0ff858a07321"
down_revision: str | Sequence[str] | None = "1bd74bd9a0cf"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_FULL_OLD = "Compiled portrait full format (~200 tokens) — used by response/planner."
_FULL_NEW = "Compiled portrait full format (analytical reading) — used by response/planner."
_BRIEF_OLD = "Compiled portrait brief format (~60 tokens) — used by secondary flows."
_BRIEF_NEW = "Compiled portrait brief format (its own claims) — used by secondary flows."
_SOURCES_OLD = (
    "Provenance of the compiled portrait: journal entries count and, per source "
    "(memories, interests, habits, relation_debriefs), status/used/total."
)
_SOURCES_NEW = (
    "Provenance of the compiled portrait: journal entries count and, per source "
    "(the nine of PORTRAIT_SOURCE_KEYS), status/used/total, plus the claims."
)


def _comment(column: str, type_: sa.types.TypeEngine, old: str, new: str) -> None:
    op.alter_column(
        "users",
        column,
        existing_type=type_,
        existing_nullable=True,
        comment=new,
        existing_comment=old,
    )


def upgrade() -> None:
    """Give the three portrait columns the comments their model declares."""
    _comment("journal_portrait_full", sa.Text(), _FULL_OLD, _FULL_NEW)
    _comment("journal_portrait_brief", sa.Text(), _BRIEF_OLD, _BRIEF_NEW)
    _comment("journal_portrait_sources", postgresql.JSONB(), _SOURCES_OLD, _SOURCES_NEW)


def downgrade() -> None:
    """Restore the previous comments."""
    _comment("journal_portrait_full", sa.Text(), _FULL_NEW, _FULL_OLD)
    _comment("journal_portrait_brief", sa.Text(), _BRIEF_NEW, _BRIEF_OLD)
    _comment("journal_portrait_sources", postgresql.JSONB(), _SOURCES_NEW, _SOURCES_OLD)
