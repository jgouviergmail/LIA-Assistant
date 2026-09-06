"""A reminder stores a RecurrenceSpec, so it can repeat.

A reminder held ONE instant (`trigger_at`) and was deleted once it fired. The
spec added here does not replace that instant — it says what to arm AFTER it.
A single occurrence answers "nothing", which is the historical behaviour
expressed as a rule rather than as a special case, so `trigger_at` stays
NOT NULL: a reminder with no future is deleted, never kept.

The backfill reads each row's own timezone, because the wall clock is what the
spec stores: `trigger_at` is UTC, `AT TIME ZONE user_timezone` gives the local
clock the reader actually asked for.

**`trigger_at` is never recomputed from the spec.** A `TimeOfDay` has no
seconds, so re-deriving the instant would move any reminder set at, say,
10:00:37. The spec answers "what next"; the stored instant stays the authority
for the occurrence already armed.

Revision ID: f0a1b2c3d4e5
Revises: e9f0a1b2c3d4
Create Date: 2026-09-06 01:00:00.000000
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "f0a1b2c3d4e5"
down_revision: str | None = "e9f0a1b2c3d4"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

#: One SQL statement rather than a Python loop: it cannot half-apply, and it
#: costs the same whatever the row count.
#:
#: `AT TIME ZONE user_timezone` turns the stored UTC instant into the local
#: wall clock — the only reading under which "10:00" means what the reader
#: asked for.
_TO_RECURRENCE = """
    UPDATE reminders SET recurrence = jsonb_build_object(
        'freq', 'once',
        'interval', 1,
        'anchor_date', to_char((trigger_at AT TIME ZONE user_timezone)::date, 'YYYY-MM-DD'),
        'byweekday', '[]'::jsonb,
        'bymonthday', '[]'::jsonb,
        'bymonth', '[]'::jsonb,
        'nth_weekday', 'null'::jsonb,
        'times', jsonb_build_object(
            'mode', 'at',
            'at', jsonb_build_array(
                jsonb_build_object(
                    'hour', extract(hour from (trigger_at AT TIME ZONE user_timezone))::int,
                    'minute', extract(minute from (trigger_at AT TIME ZONE user_timezone))::int
                )
            ),
            'step_minutes', null, 'start', null, 'end', null
        ),
        'end', jsonb_build_object('kind', 'never', 'on_date', null, 'after_count', null)
    )
"""

#: A reminder that repeats has no faithful single-instant form: dropping the
#: column would silently turn a daily reminder into a one-shot that then
#: deletes itself. The downgrade refuses rather than inventing an answer.
_REPEATING = "SELECT count(*) FROM reminders WHERE recurrence->>'freq' <> 'once'"


def upgrade() -> None:
    """Add the spec and fill it from the instant each row already carries."""
    op.add_column(
        "reminders",
        sa.Column(
            "recurrence",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=True,  # filled below, then made NOT NULL
            comment="RecurrenceSpec: which calendar days, and which moments in them.",
        ),
    )
    op.execute(_TO_RECURRENCE)
    op.alter_column("reminders", "recurrence", nullable=False)


def downgrade() -> None:
    """Drop the spec, refusing to flatten a reminder that repeats."""
    connection = op.get_bind()
    repeating = connection.execute(sa.text(_REPEATING)).scalar_one()
    if repeating:
        raise RuntimeError(
            f"{repeating} reminder(s) repeat. Dropping the recurrence would "
            "leave them as one-shot reminders that delete themselves after "
            "the next notification; delete or simplify them first."
        )
    op.drop_column("reminders", "recurrence")
