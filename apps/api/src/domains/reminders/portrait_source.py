"""The pending reminders as a portrait source (2026-10-12).

Installed into ``domains/shared/portrait_sources`` so ``journals`` reads it
without importing this domain. Reminders carry no deployment flag and no
capability switch, so the only gate is the row's own: PENDING. Every pending
reminder is rendered whole: a one-off one with its instant on the person's
clock, a repeating one with its recurrence in the person's language and
WITHOUT its next instant — that instant moves at every firing, and hashed it
reopened the consolidation after each one (review 2026-10-12). A read that
fails is ``unavailable``.
"""

from __future__ import annotations

from typing import Any
from uuid import UUID
from zoneinfo import ZoneInfo

import structlog
from sqlalchemy import select

from src.core.recurrence import RecurrenceSpec, describe
from src.core.time_utils import resolve_user_timezone
from src.domains.reminders.models import Reminder, ReminderStatus
from src.domains.shared.portrait_sources import (
    FreshnessProbe,
    PortraitSourceSection,
    empty_section,
    flat_item,
    install_portrait_source,
    portrait_lines,
)
from src.domains.users.models import User
from src.infrastructure.database.session import get_db_context

logger = structlog.get_logger(__name__)

KEY = "reminders"


async def _rows(db: Any, user_id: UUID) -> tuple[list[Reminder], ZoneInfo]:
    """Every PENDING reminder, soonest first, and the person's clock."""
    stmt = (
        select(Reminder)
        .where(Reminder.user_id == user_id, Reminder.status == ReminderStatus.PENDING.value)
        .order_by(Reminder.trigger_at.asc(), Reminder.id)
    )
    rows = list((await db.execute(stmt)).scalars().all())
    return rows, resolve_user_timezone(await db.get(User, user_id))


def _item(row: Reminder, clock: ZoneInfo, language: str, lines: dict[str, str]) -> str:
    spec = RecurrenceSpec.model_validate(row.recurrence)
    if spec.freq == "once":
        when = row.trigger_at.astimezone(clock).strftime("%Y-%m-%d %H:%M")
    else:
        when = flat_item(describe(spec, language))
    return lines["reminders_item"].format(content=flat_item(row.content), when=when)


async def read_reminders(*, user_id: UUID, language: str) -> PortraitSourceSection:
    """Render every pending reminder of one account.

    Args:
        user_id: The account.
        language: The language a recurrence is described in.

    Returns:
        The section; never raises.
    """
    try:
        async with get_db_context() as db:
            rows, clock = await _rows(db, user_id)
        if not rows:
            return empty_section(KEY, "empty")
        lines = portrait_lines()
        items = [_item(row, clock, language, lines) for row in rows]
        header = lines["reminders_header"].format(shown=len(items), total=len(items))
        return PortraitSourceSection(
            key=KEY,
            status="used",
            text="\n".join([header, *items]),
            used=len(items),
            total=len(items),
        )
    except Exception as exc:  # noqa: BLE001 — a blind source is named, never read as empty
        logger.warning("portrait_source_unavailable", source=KEY, error_type=type(exc).__name__)
        return empty_section(KEY, "unavailable")


FRESHNESS = FreshnessProbe(
    table="reminders",
    user_column="user_id",
    stamp_column="updated_at",
    # ``trigger_at`` is deliberately absent: rendered for a one-off reminder only,
    # it moves at every firing of a repeating one.
    semantic_columns=("content", "recurrence", "status"),
)

install_portrait_source(KEY, read_reminders, FRESHNESS)

__all__ = ["FRESHNESS", "KEY", "read_reminders"]
