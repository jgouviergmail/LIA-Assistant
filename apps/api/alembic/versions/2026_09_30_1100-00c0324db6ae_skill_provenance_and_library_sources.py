"""Record how a skill arrived, and where a library skill came from (ADR-327, lot 1).

Revision ID: 00c0324db6ae
Revises: 61b299a42af9
Create Date: 2026-09-30 11:00:00.000000

``skills.provenance`` names the channel that brought a skill's content —
``system``, ``authored`` (uploaded or generated in chat), ``url``, ``plugin`` or
``library`` — and the last three are third-party: their instructions never drive
a model holding the person's tools. Existing rows are backfilled from what the
schema already knows: a system skill is ``system``, a plugin's skill is
``plugin``. Every other existing user skill stays ``authored``: whether it came
from an upload or an address was never recorded, and nothing may be guessed.

``skill_library_sources`` is the 1:1 provenance of a skill installed from a
library, cascading with the skill. Comments are literals: a migration must not
move when a model's constant does.
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import UUID

revision: str = "00c0324db6ae"
down_revision: str | Sequence[str] | None = "61b299a42af9"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_PROVENANCE_CHECK = "ck_skills_provenance"
_TABLE = "skill_library_sources"


def upgrade() -> None:
    """Add and backfill ``skills.provenance``; create ``skill_library_sources``."""
    op.add_column(
        "skills",
        sa.Column(
            "provenance",
            sa.String(20),
            nullable=False,
            server_default="authored",
            comment=(
                "How the content arrived: system | authored | url | plugin | library "
                "(ADR-327). url, plugin and library are third-party."
            ),
        ),
    )
    op.execute("UPDATE skills SET provenance = 'system' WHERE is_system")
    op.execute("UPDATE skills SET provenance = 'plugin' WHERE plugin_id IS NOT NULL")
    op.create_check_constraint(
        _PROVENANCE_CHECK,
        "skills",
        "provenance IN ('system', 'authored', 'url', 'plugin', 'library') "
        "AND (provenance = 'system') = is_system",
    )

    op.create_table(
        _TABLE,
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "skill_id",
            UUID(as_uuid=True),
            sa.ForeignKey("skills.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "portal",
            sa.String(40),
            nullable=True,
            comment="The library it was found on (a declared portal key); NULL = a repository address.",
        ),
        sa.Column(
            "origin",
            sa.String(20),
            nullable=False,
            comment="Where its content was read (a declared origin key, e.g. github).",
        ),
        sa.Column(
            "repository",
            sa.String(200),
            nullable=False,
            comment="The repository the folder lives in, as the origin names it (owner/repo).",
        ),
        sa.Column(
            "ref",
            sa.String(200),
            nullable=False,
            comment="The ref an update follows: HEAD, or the branch or tag the person gave.",
        ),
        sa.Column(
            "path",
            sa.String(500),
            nullable=False,
            comment="The skill's folder inside the repository ('' = the repository root).",
        ),
        sa.Column(
            "registry_id",
            sa.String(300),
            nullable=True,
            comment="The portal's own identifier of the skill, when it came from a portal.",
        ),
        sa.Column(
            "commit_sha",
            sa.String(64),
            nullable=False,
            comment="The commit the installed content was read at.",
        ),
        sa.Column(
            "tree_sha",
            sa.String(64),
            nullable=False,
            comment="The folder's git tree SHA at that commit — what an update check compares.",
        ),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index(f"ix_{_TABLE}_skill_id", _TABLE, ["skill_id"], unique=True)


def downgrade() -> None:
    """Drop the library provenance, then the provenance column."""
    op.drop_index(f"ix_{_TABLE}_skill_id", table_name=_TABLE)
    op.drop_table(_TABLE)
    op.drop_constraint(_PROVENANCE_CHECK, "skills", type_="check")
    op.drop_column("skills", "provenance")
