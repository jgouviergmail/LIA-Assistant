"""Meeting template library, automatic selection and reformatting (ADR-259).

Three tables grow, one contract goes:

- ``meeting_templates`` gains ``description``, ``category`` and ``builtin_key``
  and LOSES ``is_default`` with its partial unique index: a user now keeps
  several templates, and the one applied by default is a preference, not a flag
  on the row (a flag needs a "one per user" index the library cannot have).
- ``meeting_preferences`` gains ``default_template_ref`` (``builtin:<key>`` or
  ``user:<uuid>``; NULL = LIA picks a template from the transcript).
- ``meetings`` records WHICH template wrote its minutes and why
  (``template_ref``, ``template_name``, ``template_selection``,
  ``template_selection_reason``) and the meeting it was derived from when the
  minutes were produced from another meeting's transcript (``source_meeting_id``,
  SET NULL on delete: the derived minutes outlive their source).

Data: no user had customized a template when this shipped (owner decision
2026-09-03), so no preference is carried over; an existing row simply joins the
library under the ``custom`` category. Historical meetings are marked
``template_selection = 'preference'`` (what applied then: the user's template),
their ``template_name`` stays NULL — the page shows the untitled-format fallback.

Every column is inert while MEETINGS_ENABLED is false, so this migration is
safe on every deployment.

Revision ID: e0f1a2b3c4d5
Revises: c8d9e0f1a2b3
Create Date: 2026-09-03 12:00:00.000000
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "e0f1a2b3c4d5"
down_revision: str | None = "c8d9e0f1a2b3"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Grow the three tables, drop the single-default contract, stamp history."""
    # --- meeting_templates: a library, not a single row ----------------------
    op.add_column("meeting_templates", sa.Column("description", sa.Text(), nullable=True))
    op.add_column(
        "meeting_templates",
        sa.Column(
            "category",
            sa.String(length=30),
            nullable=False,
            server_default="custom",
            comment="TemplateCategory value; 'custom' unless the user files it elsewhere",
        ),
    )
    op.add_column(
        "meeting_templates",
        sa.Column(
            "builtin_key",
            sa.String(length=60),
            nullable=True,
            comment="The built-in this row was duplicated from, if any",
        ),
    )
    op.drop_index("uq_meeting_templates_one_default_per_user", table_name="meeting_templates")
    op.drop_column("meeting_templates", "is_default")

    # --- meeting_preferences: the default is a preference ---------------------
    op.add_column(
        "meeting_preferences",
        sa.Column(
            "default_template_ref",
            sa.String(length=80),
            nullable=True,
            comment="builtin:<key> | user:<uuid> applied to every meeting; NULL = LIA chooses (ADR-259)",
        ),
    )

    # --- meetings: which template, why, and derived from what -----------------
    op.add_column(
        "meetings",
        sa.Column(
            "template_ref",
            sa.String(length=80),
            nullable=True,
            comment="builtin:<key> | user:<uuid> — what produced report_*",
        ),
    )
    op.add_column(
        "meetings",
        sa.Column(
            "template_name",
            sa.String(length=120),
            nullable=True,
            comment="Snapshot of the template name at synthesis time",
        ),
    )
    op.add_column(
        "meetings",
        sa.Column(
            "template_selection",
            sa.String(length=12),
            nullable=True,
            comment="auto | user | preference (TemplateSelection)",
        ),
    )
    op.add_column(
        "meetings",
        sa.Column(
            "template_selection_reason",
            sa.String(length=300),
            nullable=True,
            comment="The model's one-line justification when auto",
        ),
    )
    op.add_column(
        "meetings",
        sa.Column(
            "source_meeting_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("meetings.id", ondelete="SET NULL"),
            nullable=True,
            comment="New minutes produced from another meeting's transcript (reformat mode 'new')",
        ),
    )
    op.create_index("ix_meetings_source", "meetings", ["source_meeting_id"])

    # Historical minutes were written by the user's (single) template.
    op.execute(
        "UPDATE meetings SET template_selection = 'preference' "
        "WHERE template_snapshot IS NOT NULL AND template_selection IS NULL"
    )


def downgrade() -> None:
    """Reverse, restoring the single-default contract on one row per user."""
    op.drop_index("ix_meetings_source", table_name="meetings")
    op.drop_column("meetings", "source_meeting_id")
    op.drop_column("meetings", "template_selection_reason")
    op.drop_column("meetings", "template_selection")
    op.drop_column("meetings", "template_name")
    op.drop_column("meetings", "template_ref")

    op.drop_column("meeting_preferences", "default_template_ref")

    op.add_column(
        "meeting_templates",
        sa.Column("is_default", sa.Boolean(), nullable=False, server_default="true"),
    )
    # The partial unique index needs at most ONE default per user: the oldest
    # template keeps the flag, the others lose it.
    op.execute(
        "UPDATE meeting_templates SET is_default = false WHERE id NOT IN ("
        "SELECT DISTINCT ON (user_id) id FROM meeting_templates ORDER BY user_id, created_at, id)"
    )
    op.create_index(
        "uq_meeting_templates_one_default_per_user",
        "meeting_templates",
        ["user_id"],
        unique=True,
        postgresql_where=sa.text("is_default = true"),
    )
    op.drop_column("meeting_templates", "builtin_key")
    op.drop_column("meeting_templates", "category")
    op.drop_column("meeting_templates", "description")
