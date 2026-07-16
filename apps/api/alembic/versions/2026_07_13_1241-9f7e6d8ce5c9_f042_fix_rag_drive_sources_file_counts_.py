"""F042 fix rag_drive_sources file counts NOT NULL

Revision ID: 9f7e6d8ce5c9
Revises: 49f8b99d2e17
Create Date: 2026-07-13 12:41:41.331313

The ORM declares ``rag_drive_sources.file_count`` and ``synced_file_count`` as
``nullable=False`` (Integer, default 0), but the creating migration
(``add_rag_drive_sources``) omitted ``nullable=False`` on the columns, so the
schema left them NULLable — a genuine model↔schema drift surfaced by the
structural-drift gate (audit F042). This migration aligns the schema with the
model. A defensive back-fill coalesces any pre-existing NULLs to 0 before the
constraint is added so the ALTER cannot fail on live data.
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "9f7e6d8ce5c9"
down_revision: str | None = "49f8b99d2e17"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_COLUMNS = ("file_count", "synced_file_count")


def upgrade() -> None:
    """Back-fill NULLs to 0, then enforce NOT NULL to match the ORM."""
    for column in _COLUMNS:
        op.execute(sa.text(f"UPDATE rag_drive_sources SET {column} = 0 WHERE {column} IS NULL"))
        op.alter_column(
            "rag_drive_sources",
            column,
            existing_type=sa.Integer(),
            nullable=False,
            existing_server_default=sa.text("0"),
        )


def downgrade() -> None:
    """Restore the NULLable columns."""
    for column in _COLUMNS:
        op.alter_column(
            "rag_drive_sources",
            column,
            existing_type=sa.Integer(),
            nullable=True,
            existing_server_default=sa.text("0"),
        )
