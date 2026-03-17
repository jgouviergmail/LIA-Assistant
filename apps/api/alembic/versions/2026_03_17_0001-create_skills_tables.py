"""Create skills + user_skill_states tables, drop legacy disabled_skills column.

Revision ID: skills_tables_001
Revises: sub_agents_003
Create Date: 2026-03-17

Replaces the JSONB-on-User pattern (disabled_skills) with two normalized
tables: ``skills`` (skill registry) and ``user_skill_states`` (per-user
activation state).

This migration:
1. Creates the skills and user_skill_states tables with indexes
2. Drops the legacy disabled_skills JSONB column from users

Note: The system_disabled_skills column was never deployed (migration deleted),
so it is NOT dropped here. Data population from disk is handled at application
startup via SkillPreferenceService.sync_from_disk(), which also reads the
disabled_skills column if it still exists to preserve user preferences.
However, since we need the data before dropping, we store it in a temp table.
"""

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB, UUID

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "skills_tables_001"
down_revision: str | None = "system_disabled_skills_001"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Create normalized skills tables, preserve user prefs, drop legacy column."""
    # ---- 1. Create skills table ----
    op.create_table(
        "skills",
        sa.Column("id", UUID(as_uuid=True), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column("name", sa.String(100), nullable=False),
        sa.Column("is_system", sa.Boolean(), nullable=False, server_default="true"),
        sa.Column("owner_id", UUID(as_uuid=True), nullable=True),
        sa.Column("admin_enabled", sa.Boolean(), nullable=False, server_default="true"),
        sa.Column("description", sa.String(1024), nullable=False),
        sa.Column("descriptions", JSONB(), nullable=True),
        sa.ForeignKeyConstraint(["owner_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_skills_name", "skills", ["name"], unique=True)
    op.create_index("ix_skills_owner_id", "skills", ["owner_id"])
    op.create_index(
        "ix_skills_system_enabled",
        "skills",
        ["is_system", "admin_enabled"],
        postgresql_where=sa.text("is_system = true"),
    )

    # ---- 2. Create user_skill_states table ----
    op.create_table(
        "user_skill_states",
        sa.Column("id", UUID(as_uuid=True), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column("user_id", UUID(as_uuid=True), nullable=False),
        sa.Column("skill_id", UUID(as_uuid=True), nullable=False),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default="true"),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["skill_id"], ["skills.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_user_skill_states_user_id", "user_skill_states", ["user_id"])
    op.create_index("ix_user_skill_states_skill_id", "user_skill_states", ["skill_id"])
    op.create_index(
        "ix_user_skill_states_user_skill",
        "user_skill_states",
        ["user_id", "skill_id"],
        unique=True,
    )
    op.create_index(
        "ix_user_skill_states_active",
        "user_skill_states",
        ["user_id"],
        postgresql_where=sa.text("is_active = true"),
    )

    # ---- 3. Preserve legacy JSONB data in helper tables ----
    # Save per-user preferences so the startup sync can restore them.
    op.execute(
        sa.text("""
            CREATE TABLE IF NOT EXISTS _legacy_disabled_skills AS
            SELECT id AS user_id, disabled_skills
            FROM users
            WHERE disabled_skills IS NOT NULL AND disabled_skills != '[]'::jsonb
        """)
    )
    op.execute(
        sa.text("""
            CREATE TABLE IF NOT EXISTS _legacy_system_disabled_skills AS
            SELECT id AS user_id, system_disabled_skills
            FROM users
            WHERE is_superuser = true
              AND system_disabled_skills IS NOT NULL
              AND system_disabled_skills != '[]'::jsonb
        """)
    )

    # ---- 4. Drop legacy JSONB columns ----
    op.drop_column("users", "disabled_skills")
    op.drop_column("users", "system_disabled_skills")


def downgrade() -> None:
    """Recreate legacy columns and drop normalized tables."""
    # Recreate legacy columns
    op.add_column(
        "users",
        sa.Column(
            "disabled_skills",
            JSONB(),
            nullable=False,
            server_default="[]",
        ),
    )
    op.add_column(
        "users",
        sa.Column(
            "system_disabled_skills",
            JSONB(),
            nullable=False,
            server_default="[]",
        ),
    )

    # Restore data from helper tables if they exist
    op.execute(
        sa.text("""
            UPDATE users u
            SET disabled_skills = lds.disabled_skills
            FROM _legacy_disabled_skills lds
            WHERE u.id = lds.user_id
        """)
    )
    op.execute(
        sa.text("""
            UPDATE users u
            SET system_disabled_skills = lsds.system_disabled_skills
            FROM _legacy_system_disabled_skills lsds
            WHERE u.id = lsds.user_id
        """)
    )

    # Drop helper tables
    op.execute(sa.text("DROP TABLE IF EXISTS _legacy_disabled_skills"))
    op.execute(sa.text("DROP TABLE IF EXISTS _legacy_system_disabled_skills"))

    # Drop normalized tables (order: child first)
    op.drop_index("ix_user_skill_states_active", table_name="user_skill_states")
    op.drop_index("ix_user_skill_states_user_skill", table_name="user_skill_states")
    op.drop_index("ix_user_skill_states_skill_id", table_name="user_skill_states")
    op.drop_index("ix_user_skill_states_user_id", table_name="user_skill_states")
    op.drop_table("user_skill_states")

    op.drop_index("ix_skills_system_enabled", table_name="skills")
    op.drop_index("ix_skills_owner_id", table_name="skills")
    op.drop_index("ix_skills_name", table_name="skills")
    op.drop_table("skills")
