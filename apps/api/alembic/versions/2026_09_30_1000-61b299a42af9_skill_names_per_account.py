"""A skill name is unique per account, not per instance (ADR-327, lot 0).

Revision ID: 61b299a42af9
Revises: 7b885c320074
Create Date: 2026-09-30 10:00:00.000000

``skills.name`` carried ONE unique index for the whole instance, so a second
person could never keep a skill the first had installed under the same name.
The rule becomes per scope: a system name is unique among system skills, a
person's names are unique among their own. Both indexes rely on
``is_system ⇔ owner_id IS NULL``, which every write path already respects and
which the CHECK now pins (the owner FK cascades the whole row, so no
foreign-key action can leave one between the two states).

The downgrade restores the instance-wide index, which cannot hold two
accounts' skills of one name: it refuses, naming the count, rather than failing
half-way on the index build.
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "61b299a42af9"
down_revision: str | Sequence[str] | None = "7b885c320074"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_CHECK = "ck_skills_system_has_no_owner"


def upgrade() -> None:
    """Swap the instance-wide name index for two per-scope ones plus the CHECK."""
    op.drop_index("ix_skills_name", table_name="skills")
    op.create_index("ix_skills_name", "skills", ["name"])
    op.create_index(
        "uq_skills_system_name",
        "skills",
        ["name"],
        unique=True,
        postgresql_where=sa.text("owner_id IS NULL"),
    )
    op.create_index(
        "uq_skills_owner_name",
        "skills",
        ["owner_id", "name"],
        unique=True,
        postgresql_where=sa.text("owner_id IS NOT NULL"),
    )
    op.create_check_constraint(_CHECK, "skills", "is_system = (owner_id IS NULL)")


def downgrade() -> None:
    """Restore the instance-wide unique name, when the data still allows it."""
    shared = (
        op.get_bind()
        .execute(
            sa.text(
                "SELECT count(*) FROM (SELECT name FROM skills GROUP BY name HAVING count(*) > 1) d"
            )
        )
        .scalar_one()
    )
    if shared:
        raise RuntimeError(
            f"{shared} skill name(s) are held by more than one scope; an instance-wide "
            "unique index cannot hold them. Rename or delete those skills first."
        )
    op.drop_constraint(_CHECK, "skills", type_="check")
    op.drop_index("uq_skills_owner_name", table_name="skills")
    op.drop_index("uq_skills_system_name", table_name="skills")
    op.drop_index("ix_skills_name", table_name="skills")
    op.create_index("ix_skills_name", "skills", ["name"], unique=True)
