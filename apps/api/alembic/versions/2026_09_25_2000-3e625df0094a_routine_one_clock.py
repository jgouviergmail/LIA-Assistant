"""A routine runs on ONE clock: its schedule, or the system's checks (ADR-322).

Revision ID: 3e625df0094a
Revises: 343c834a3a07
Create Date: 2026-09-25 20:00:00.000000

A condition routine used to carry a recurrence too — « cron stays the clock for
both kinds » (N-07 phase 1) — so its condition was read only at the hours the
schedule named: a mail watch set up from the briefing was checked at 09:00 and
17:00 and could announce an awaited reply sixteen hours late. The system now
checks a condition itself (``domains/scheduled_actions/trigger.py``) and the
schedule goes.

What the upgrade does, and why each step is safe:

- ``recurrence`` becomes nullable, and every CONDITION routine loses it. What
  that schedule still MEANT is carried over: its end. A series ending on a date
  keeps that date as ``condition_config.until``; a series ending after N
  instants (or a single occurrence) ends on the local day of its last instant,
  computed by the engine that armed it; a series with no end has none. The
  check HOURS are what is dropped — deliberately, they were the defect.
- a watch whose last day is already over has nothing left: its trigger goes to
  NULL and the executor's own sweep closes it (``close_finished``), exactly as
  an exhausted series always was.
- a watch still running is brought forward to its first check within the next
  ten minutes, spread at random so a deploy does not check every mailbox in the
  same second — rather than waiting until its old schedule's next hour.
- a TIME routine carrying a condition loses it — including the JSON ``null``
  the service wrote for every time routine it created (a Python ``None`` on a
  JSONB column is the JSON ``null``, which ``IS NULL`` does not match; the
  model now stores SQL NULL, ``none_as_null``) — and a CONDITION routine with
  no condition — a row no writer produces, which never ran — becomes an inert
  time routine, paused and marked in error, instead of failing the constraint.
- the CHECK ``ck_scheduled_actions_one_clock`` then holds the pairing for every
  writer, the API schema's rule (``trigger_mode_refusal``) stated to the table.

The downgrade gives each condition routine back a schedule — every day at 09:00
and 17:00, the fallback the briefing's watch used, ending on its ``until`` —
and drops the constraint. Two things are lost, written here rather than
discovered: the hours are invented, because the previous code cannot run a
condition without them; and the fact ledger means nothing to that code, which
reads a set fingerprint — so its first check serves once what it finds, the
same recoverable duplicate the upgrade accepts in the other direction.
"""

from __future__ import annotations

import json
import logging
from collections.abc import Sequence
from datetime import UTC, date, datetime
from typing import Any
from zoneinfo import ZoneInfo

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

logger = logging.getLogger("alembic.runtime.migration")

# revision identifiers, used by Alembic.
revision: str = "3e625df0094a"
down_revision: str | None = "343c834a3a07"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_TABLE = "scheduled_actions"
_CHECK = "ck_scheduled_actions_one_clock"
_CHECK_CONDITION = (
    "(trigger_kind = 'time' AND recurrence IS NOT NULL AND condition_config IS NULL)"
    " OR (trigger_kind = 'condition' AND recurrence IS NULL"
    " AND condition_config IS NOT NULL)"
)

#: Column comments, new then old — the model mirrors the new ones EXACTLY.
_COMMENTS: dict[str, tuple[str, str]] = {
    "recurrence": (
        "TIME kind only: RecurrenceSpec, which days and moments. NULL for a condition.",
        "RecurrenceSpec: which calendar days, and which moments in them.",
    ),
    "trigger_kind": (
        "time = runs on its recurrence; condition = checked by the system (ADR-322)",
        "time = fire at every tick; condition = fire only when met (N-07)",
    ),
    "condition_config": (
        "CONDITION kind only: {type, params, until} — schema-validated.",
        "CONDITION kind only: {type, params} — schema-validated.",
    ),
    "condition_state": (
        "Fact ledger: {seen, last_checked_at, last_check_error, last_fired_at}.",
        "Dedup ledger: {last_fingerprint, last_fired_at}.",
    ),
}
_SLOT_COMMENTS = (
    "The instant this run served (UTC): a time routine's slot, a condition "
    "routine's check; NULL = a rehearsal.",
    "The scheduled instant this run served (UTC); NULL = a rehearsal.",
)

#: The window a running watch's first check is spread over. The migration's
#: own figure — the setting it echoes may change, a migration never does.
BRING_FORWARD_MINUTES = 10

#: The first check of a running watch, spread over that window.
_BRING_FORWARD = f"""
    UPDATE scheduled_actions
       SET next_trigger_at = LEAST(
             next_trigger_at, now() + random() * interval '{BRING_FORWARD_MINUTES} minutes'
           )
     WHERE trigger_kind = 'condition'
       AND is_enabled = true
       AND status = 'active'
       AND next_trigger_at IS NOT NULL
"""

#: Rows no writer produces, repaired so the constraint can hold.
_STRAY_CONDITION_ON_TIME = """
    UPDATE scheduled_actions SET condition_config = NULL, condition_state = NULL
     WHERE trigger_kind = 'time' AND condition_config IS NOT NULL
"""
_CONDITION_WITHOUT_CONDITION = """
    UPDATE scheduled_actions
       SET trigger_kind = 'time', is_enabled = false, status = 'error',
           condition_config = NULL, condition_state = NULL,
           last_error = 'Condition missing: paused by the ADR-322 upgrade.'
     WHERE trigger_kind = 'condition'
       AND (condition_config IS NULL OR jsonb_typeof(condition_config) = 'null')
       AND recurrence IS NOT NULL
"""

#: The fallback schedule the downgrade gives a condition routine back.
DOWNGRADE_HOURS: tuple[int, ...] = (9, 17)


def until_of(recurrence: dict[str, Any], timezone: str) -> date | None:
    """The last local day a condition routine's old schedule reached.

    Args:
        recurrence: The stored ``RecurrenceSpec``.
        timezone: The routine's IANA zone.

    Returns:
        The day, or ``None`` when the series had no end (or cannot be read —
        an unreadable schedule keeps watching rather than stopping).
    """
    from src.core.recurrence import RecurrenceSpec, series

    try:
        spec = RecurrenceSpec.model_validate(recurrence)
        zone = ZoneInfo(timezone)
    except Exception:  # noqa: BLE001 — a row the migration cannot read keeps watching
        return None
    if spec.end.kind == "on_date":
        return spec.end.on_date
    if spec.end.kind != "after_count" and spec.freq != "once":
        return None
    last: datetime | None = None
    for instant in series(spec, zone):
        last = instant
    return last.astimezone(zone).date() if last is not None else spec.anchor_date


def schedule_of(until: date | None, anchor: date) -> dict[str, Any]:
    """The schedule a downgrade gives a condition routine back.

    Args:
        until: Its last watched day, if any.
        anchor: The day its series starts — moved back to ``until`` when it
            falls after it, since a series may not end before it starts.

    Returns:
        A ``RecurrenceSpec`` as the column stores it.
    """
    from src.core.recurrence import DailyTimes, RecurrenceSpec, SeriesEnd, TimeOfDay

    return RecurrenceSpec(
        freq="daily",
        anchor_date=min(anchor, until) if until else anchor,
        times=DailyTimes(
            mode="at", at=tuple(TimeOfDay(hour=hour, minute=0) for hour in DOWNGRADE_HOURS)
        ),
        end=SeriesEnd(kind="on_date", on_date=until) if until else SeriesEnd(),
    ).model_dump(mode="json")


def _comment_columns(*, new: bool) -> None:
    index = 0 if new else 1
    for column, comments in _COMMENTS.items():
        op.alter_column(
            _TABLE,
            column,
            existing_type=(
                postgresql.JSONB(astext_type=sa.Text())
                if column != "trigger_kind"
                else sa.String(20)
            ),
            comment=comments[index],
            existing_comment=comments[1 - index],
        )
    op.alter_column(
        "scheduled_action_runs",
        "slot_at",
        existing_type=sa.DateTime(timezone=True),
        comment=_SLOT_COMMENTS[index],
        existing_comment=_SLOT_COMMENTS[1 - index],
    )


def upgrade() -> None:
    """Condition routines lose their schedule and keep its end."""
    op.alter_column(
        _TABLE, "recurrence", existing_type=postgresql.JSONB(astext_type=sa.Text()), nullable=True
    )
    _comment_columns(new=True)
    connection = op.get_bind()
    connection.execute(sa.text(_STRAY_CONDITION_ON_TIME))
    connection.execute(sa.text(_CONDITION_WITHOUT_CONDITION))

    today = datetime.now(UTC)
    rows = connection.execute(
        sa.text(
            "SELECT id, recurrence, condition_config, user_timezone FROM scheduled_actions "
            "WHERE trigger_kind = 'condition' AND recurrence IS NOT NULL"
        ).columns(
            sa.column("id", postgresql.UUID(as_uuid=True)),
            sa.column("recurrence", postgresql.JSONB),
            sa.column("condition_config", postgresql.JSONB),
            sa.column("user_timezone", sa.String),
        )
    ).all()
    ended = 0
    for row in rows:
        until = until_of(row.recurrence, row.user_timezone)
        config = {
            key: value for key, value in (row.condition_config or {}).items() if key != "until"
        }
        if until is not None:
            config["until"] = until.isoformat()
        over = until is not None and until < today.astimezone(ZoneInfo(row.user_timezone)).date()
        ended += int(over)
        connection.execute(
            sa.text(
                "UPDATE scheduled_actions SET recurrence = NULL, "
                "condition_config = CAST(:config AS JSONB)"
                + (", next_trigger_at = NULL" if over else "")
                + " WHERE id = :id"
            ),
            {"config": json.dumps(config), "id": row.id},
        )
    connection.execute(sa.text(_BRING_FORWARD))
    op.create_check_constraint(_CHECK, _TABLE, _CHECK_CONDITION)
    logger.info("routine one clock: %d condition routines rewritten, %d ended", len(rows), ended)


def downgrade() -> None:
    """Condition routines get a schedule back, ending on their last day."""
    op.drop_constraint(_CHECK, _TABLE, type_="check")
    connection = op.get_bind()
    rows = connection.execute(
        sa.text(
            "SELECT id, condition_config, user_timezone, created_at FROM scheduled_actions "
            "WHERE trigger_kind = 'condition'"
        ).columns(
            sa.column("id", postgresql.UUID(as_uuid=True)),
            sa.column("condition_config", postgresql.JSONB),
            sa.column("user_timezone", sa.String),
            sa.column("created_at", sa.DateTime(timezone=True)),
        )
    ).all()
    for row in rows:
        config = dict(row.condition_config or {})
        raw_until = config.pop("until", None)
        until = date.fromisoformat(raw_until) if isinstance(raw_until, str) else None
        anchor = row.created_at.astimezone(ZoneInfo(row.user_timezone)).date()
        connection.execute(
            sa.text(
                "UPDATE scheduled_actions SET recurrence = CAST(:recurrence AS JSONB), "
                "condition_config = CAST(:config AS JSONB) WHERE id = :id"
            ),
            {
                "recurrence": json.dumps(schedule_of(until, anchor)),
                "config": json.dumps(config),
                "id": row.id,
            },
        )
    _comment_columns(new=False)
    op.alter_column(
        _TABLE, "recurrence", existing_type=postgresql.JSONB(astext_type=sa.Text()), nullable=False
    )
