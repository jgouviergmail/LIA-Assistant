"""A routine stores a RecurrenceSpec, not three cron columns.

`days_of_week` + `trigger_hour` + `trigger_minute` could express one time a
day on a set of weekdays and nothing else. The replacement is a JSONB
`RecurrenceSpec` (`src/core/recurrence`), and the conversion is a strict
equivalence: a weekly rule, interval 1, on the same days, at the one time.

Verified on the real dev rows 2026-09-06: the produced JSON round-trips through
`RecurrenceSpec`, and the instants it yields lose nothing against the cron
engine over three reference dates.

`next_trigger_at` becomes nullable — NULL means nothing follows — and the
partial index that serves the poll gains `next_trigger_at IS NOT NULL`, since
`NULL <= now()` is UNKNOWN and such a row can never match.

Revision ID: e9f0a1b2c3d4
Revises: d8e9f0a1b2c3
Create Date: 2026-09-06 00:00:00.000000
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "e9f0a1b2c3d4"
down_revision: str | None = "d8e9f0a1b2c3"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

#: The conversion, as one SQL expression. Pure SQL rather than a Python loop:
#: it runs in one statement whatever the row count, and it cannot half-apply.
_TO_RECURRENCE = """
    UPDATE scheduled_actions SET recurrence = jsonb_build_object(
        'freq', 'weekly',
        'interval', 1,
        'anchor_date', to_char((created_at AT TIME ZONE user_timezone)::date, 'YYYY-MM-DD'),
        'byweekday', to_jsonb(days_of_week),
        'bymonthday', '[]'::jsonb,
        'bymonth', '[]'::jsonb,
        'nth_weekday', 'null'::jsonb,
        'times', jsonb_build_object(
            'mode', 'at',
            'at', jsonb_build_array(
                jsonb_build_object('hour', trigger_hour, 'minute', trigger_minute)
            ),
            'step_minutes', null, 'start', null, 'end', null
        ),
        'end', jsonb_build_object('kind', 'never', 'on_date', null, 'after_count', null)
    )
"""

#: The reverse, for a routine the new model can still express in the old one.
#: A recurrence the cron columns cannot hold (monthly, several times a day)
#: has no faithful answer, so the downgrade REFUSES rather than inventing one.
_FROM_RECURRENCE = """
    UPDATE scheduled_actions SET
        days_of_week = ARRAY(
            SELECT jsonb_array_elements_text(recurrence->'byweekday')::smallint
        ),
        trigger_hour = (recurrence->'times'->'at'->0->>'hour')::smallint,
        trigger_minute = (recurrence->'times'->'at'->0->>'minute')::smallint
"""

_DOWNGRADABLE = """
    SELECT count(*) FROM scheduled_actions
     WHERE recurrence->>'freq' <> 'weekly'
        OR (recurrence->>'interval')::int <> 1
        OR recurrence->'times'->>'mode' <> 'at'
        OR jsonb_array_length(recurrence->'times'->'at') <> 1
        OR recurrence->'end'->>'kind' <> 'never'
"""


def upgrade() -> None:
    """Add the spec, fill it from the cron columns, drop them."""
    op.add_column(
        "scheduled_actions",
        sa.Column(
            "recurrence",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=True,  # filled below, then made NOT NULL
            comment="RecurrenceSpec: which calendar days, and which moments in them.",
        ),
    )
    op.execute(_TO_RECURRENCE)
    op.alter_column("scheduled_actions", "recurrence", nullable=False)

    op.drop_column("scheduled_actions", "days_of_week")
    op.drop_column("scheduled_actions", "trigger_hour")
    op.drop_column("scheduled_actions", "trigger_minute")

    op.alter_column(
        "scheduled_actions",
        "next_trigger_at",
        existing_type=sa.DateTime(timezone=True),
        nullable=True,
        comment="Next execution (UTC); NULL = nothing follows.",
    )

    # The poll reads `next_trigger_at <= now()`, which is UNKNOWN for a NULL:
    # such a row can never match, so it has no business in the index.
    op.drop_index("ix_scheduled_actions_due", table_name="scheduled_actions")
    op.create_index(
        "ix_scheduled_actions_due",
        "scheduled_actions",
        ["next_trigger_at"],
        postgresql_where=sa.text(
            "is_enabled = true AND status = 'active' AND next_trigger_at IS NOT NULL"
        ),
    )


def downgrade() -> None:
    """Restore the cron columns, refusing what they cannot express."""
    connection = op.get_bind()
    blocking = connection.execute(sa.text(_DOWNGRADABLE)).scalar_one()
    if blocking:
        raise RuntimeError(
            f"{blocking} routine(s) use a recurrence the cron columns cannot "
            "express (monthly, an interval, several times a day, or an end "
            "date). Downgrading would silently rewrite their schedule; delete "
            "or simplify them first."
        )

    op.add_column(
        "scheduled_actions",
        sa.Column("days_of_week", postgresql.ARRAY(sa.SmallInteger()), nullable=True),
    )
    op.add_column("scheduled_actions", sa.Column("trigger_hour", sa.SmallInteger(), nullable=True))
    op.add_column(
        "scheduled_actions", sa.Column("trigger_minute", sa.SmallInteger(), nullable=True)
    )
    op.execute(_FROM_RECURRENCE)
    for column in ("days_of_week", "trigger_hour", "trigger_minute"):
        op.alter_column("scheduled_actions", column, nullable=False)

    op.execute("UPDATE scheduled_actions SET next_trigger_at = now() WHERE next_trigger_at IS NULL")
    op.alter_column(
        "scheduled_actions",
        "next_trigger_at",
        existing_type=sa.DateTime(timezone=True),
        nullable=False,
    )
    op.drop_column("scheduled_actions", "recurrence")

    op.drop_index("ix_scheduled_actions_due", table_name="scheduled_actions")
    op.create_index(
        "ix_scheduled_actions_due",
        "scheduled_actions",
        ["next_trigger_at"],
        postgresql_where=sa.text("is_enabled = true AND status = 'active'"),
    )
