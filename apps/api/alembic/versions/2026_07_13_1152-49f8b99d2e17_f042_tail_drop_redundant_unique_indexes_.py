"""F042 tail: drop redundant non-unique indexes + admin_audit_log.details -> JSONB

Revision ID: 49f8b99d2e17
Revises: 320bf8a052a4
Create Date: 2026-07-13 11:52:38.354493

Five columns each carried BOTH a unique constraint (uq_.../..._key) AND a
redundant *non-unique* index (ix_<table>_<col>) on the same single column — a
historical artifact. Uniqueness is enforced solely by the constraints (their
backing unique index already serves equality lookups), so the extra non-unique
indexes are pure write overhead. This migration drops the five redundant
indexes; the models now declare the uniqueness via an explicit
``UniqueConstraint`` matching the existing constraint names, so autogenerate no
longer reports the constraints as "removed" (audit F042 tail).

It also aligns ``admin_audit_log.details`` with its model (JSONB, the codebase
standard) — the column had lagged at plain ``json``.

This migration is intentionally hand-written: ``--autogenerate`` also emits
hundreds of ``server_default``/``comment`` alterations (compare_server_default
false positives + comment drift) that are out of scope here and tracked
separately.
"""

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "49f8b99d2e17"
down_revision: str | None = "320bf8a052a4"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


# (index_name, table_name, column) for the five redundant non-unique indexes.
_REDUNDANT_INDEXES = (
    ("ix_conversations_user_id", "conversations", "user_id"),
    ("ix_user_statistics_user_id", "user_statistics", "user_id"),
    ("ix_message_token_summary_run_id", "message_token_summary", "run_id"),
    ("ix_system_settings_key", "system_settings", "key"),
    ("ix_connector_global_config_connector_type", "connector_global_config", "connector_type"),
)


def upgrade() -> None:
    """Drop the redundant non-unique indexes and widen details to JSONB."""
    for index_name, table_name, _column in _REDUNDANT_INDEXES:
        op.drop_index(index_name, table_name=table_name)

    op.alter_column(
        "admin_audit_log",
        "details",
        existing_type=postgresql.JSON(astext_type=sa.Text()),
        type_=postgresql.JSONB(astext_type=sa.Text()),
        existing_nullable=True,
        postgresql_using="details::jsonb",
    )


def downgrade() -> None:
    """Recreate the non-unique indexes and revert details to JSON."""
    op.alter_column(
        "admin_audit_log",
        "details",
        existing_type=postgresql.JSONB(astext_type=sa.Text()),
        type_=postgresql.JSON(astext_type=sa.Text()),
        existing_nullable=True,
        postgresql_using="details::json",
    )

    for index_name, table_name, column in _REDUNDANT_INDEXES:
        op.create_index(index_name, table_name, [column], unique=False)
