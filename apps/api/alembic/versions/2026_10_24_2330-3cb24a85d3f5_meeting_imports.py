"""One meeting import in progress per account (owner request 2026-10-24).

A meeting can now be imported from a WAV, MP3 or M4A file: the row is
``uploading`` while the file travels in chunks, exactly as it is ``recording``
while a capture streams. The columns are ``native_enum=False`` VARCHAR(20)
without a CHECK constraint (measured on the dev database), so the new status
and the three ``import_*`` formats need no DDL; what does is the guarantee that
an account uploads ONE file at a time, held by the database like the
one-recording rule — a partial unique index on the member NAME.

The downgrade leaves rows the previous code can read: an import still uploading
becomes ``failed`` (``import_incomplete``), and an imported meeting keeps its
normalized audio, which is WebM/Opus like a browser recording's, under that
format's name.

Revision ID: 3cb24a85d3f5
Revises: 213b9ac595c5
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "3cb24a85d3f5"
down_revision: str | None = "213b9ac595c5"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_index(
        "uq_meetings_one_import_per_user",
        "meetings",
        ["user_id"],
        unique=True,
        postgresql_where=sa.text("status = 'UPLOADING'"),
    )


def downgrade() -> None:
    op.execute(
        "UPDATE meetings SET status = 'FAILED', last_error_code = 'import_incomplete' "
        "WHERE status = 'UPLOADING'"
    )
    op.execute(
        "UPDATE meetings SET audio_format = 'WEBM_OPUS' "
        "WHERE audio_format IN ('IMPORT_WAV', 'IMPORT_MP3', 'IMPORT_M4A')"
    )
    op.drop_index("uq_meetings_one_import_per_user", table_name="meetings")
