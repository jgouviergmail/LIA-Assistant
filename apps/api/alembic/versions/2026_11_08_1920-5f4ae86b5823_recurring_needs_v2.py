"""Recurring habits become recurring needs; the offer mute leaves (ADR-375).

Revision ID: 5f4ae86b5823
Revises: e09361bae915
Create Date: 2026-11-08 19:20:00.000000

A ``recurring_request`` row used to carry a LOCKED HOUR (payload v1: ``shape``,
``trigger_hour``, ``days_of_week``, ``offer_dates``); it now describes a need
(payload v2: ``cadence``, ``usual_hour``, ``part_of_day``, ...). Every reader
fails closed on an unknown version, so no v1 row may survive this revision:

- an ACTIVE v1 row is derived data: it is deleted, and the next nightly
  recompute relearns it from the ledger if the need still holds;
- a PAUSED or BLOCKED v1 row is the person's decision: it is CONVERTED, so the
  pause or the refusal survives, with the descriptors v1 carried.

``muted_until_reproof`` served the missed-routine offer only, retired with it.
The conversion is frozen here (no application import), so a replay never
depends on later code. Downgrade restores the column; v2 payloads stay v2
(the conversion is lossy by nature), ACTIVE ones are deleted so the previous
code relearns them.
"""

import json
import math
from collections.abc import Sequence
from datetime import datetime

import sqlalchemy as sa
from alembic import op

revision: str = "5f4ae86b5823"
down_revision: str | Sequence[str] | None = "e09361bae915"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_CADENCE = {"daily": "daily", "workdays": "weekdays", "weekly": "weekly", "intermittent": "daily"}


def _part_of_day(hour: float | None) -> str:
    if hour is None:
        return "any"
    if 5 <= hour < 12:
        return "morning"
    if 12 <= hour < 18:
        return "afternoon"
    if 18 <= hour < 23:
        return "evening"
    return "night"


def _v2(key: str, payload: dict, last_observed_at: datetime) -> dict:
    """The v2 payload a v1 row converts to — frozen, no application import."""
    hour = payload.get("trigger_hour")
    hour = float(hour) if isinstance(hour, int | float) else None
    shape = str(payload.get("shape") or "daily")
    days = payload.get("days_of_week") or []
    weekday = days[0] if shape == "weekly" and days and isinstance(days[0], int) else None
    distinct = int(payload.get("distinct_days") or 0)
    converted = {
        "version": 2,
        "domain": key,
        "cadence": "weekly" if weekday is not None else _CADENCE.get(shape, "daily"),
        "weekday": weekday,
        "usual_hour": round(hour, 2) if hour is not None else 12.0,
        "prefill_hour": math.floor((hour if hour is not None else 12.0) * 4) / 4,
        "part_of_day": _part_of_day(hour),
        "distinct_days": distinct,
        "active_days": distinct,
        "occurrences": int(payload.get("occurrences") or distinct),
        "at_automation_bar": False,
        "last_day": last_observed_at.date().isoformat(),
    }
    if isinstance(payload.get("usual_intent"), str):
        converted["usual_intent"] = payload["usual_intent"]
    return converted


def upgrade() -> None:
    """Delete ACTIVE v1 needs, convert the person's PAUSED/BLOCKED ones, drop the mute."""
    bind = op.get_bind()
    rows = bind.execute(
        sa.text(
            "SELECT id, key, status, payload, last_observed_at FROM user_habits "
            "WHERE kind = 'recurring_request' AND COALESCE((payload->>'version')::int, 1) < 2"
        )
    ).all()
    for row_id, key, status, payload, last_observed_at in rows:
        if status == "active":
            bind.execute(sa.text("DELETE FROM user_habits WHERE id = :id"), {"id": row_id})
            continue
        bind.execute(
            sa.text("UPDATE user_habits SET payload = CAST(:payload AS jsonb) WHERE id = :id"),
            {"id": row_id, "payload": json.dumps(_v2(key, payload or {}, last_observed_at))},
        )
    op.drop_column("user_habits", "muted_until_reproof")


def downgrade() -> None:
    """Restore the mute column; ACTIVE v2 needs are deleted for the old lock to relearn."""
    op.add_column(
        "user_habits",
        sa.Column(
            "muted_until_reproof",
            sa.Boolean(),
            nullable=False,
            server_default=sa.false(),
            comment="Deviation stop-rule: type-1 offers muted until re-occurrence.",
        ),
    )
    op.execute(
        "DELETE FROM user_habits WHERE kind = 'recurring_request' AND status = 'active' "
        "AND (payload->>'version')::int = 2"
    )
