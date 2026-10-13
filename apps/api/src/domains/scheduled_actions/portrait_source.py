"""The routines as a portrait source: what the person automated (2026-10-12).

Installed into ``domains/shared/portrait_sources`` so ``journals`` reads it
without importing this domain. Scheduled actions carry no deployment flag and
no capability switch (CLAUDE.md: the router is always wired), so the only gate
is the row's own: ACTIVE and enabled. Every routine is rendered whole with its
clock — the recurrence in the person's language for a time routine, the
condition for a condition routine — and its instruction; a read that fails is
``unavailable``.
"""

from __future__ import annotations

from typing import Any
from uuid import UUID

import structlog
from sqlalchemy import select

from src.core.recurrence import RecurrenceSpec, describe
from src.domains.scheduled_actions.models import (
    ScheduledAction,
    ScheduledActionStatus,
    TriggerKind,
)
from src.domains.shared.portrait_sources import (
    FreshnessProbe,
    PortraitSourceSection,
    empty_section,
    flat_item,
    install_portrait_source,
    portrait_lines,
)
from src.infrastructure.database.session import get_db_context

logger = structlog.get_logger(__name__)

KEY = "routines"


async def _rows(db: Any, user_id: UUID) -> list[ScheduledAction]:
    """Every ACTIVE, enabled routine, next instant first (NULLs last), then id."""
    stmt = (
        select(ScheduledAction)
        .where(
            ScheduledAction.user_id == user_id,
            ScheduledAction.status == ScheduledActionStatus.ACTIVE.value,
            ScheduledAction.is_enabled.is_(True),
        )
        .order_by(ScheduledAction.next_trigger_at.asc().nulls_last(), ScheduledAction.id)
    )
    return list((await db.execute(stmt)).scalars().all())


def _schedule(row: ScheduledAction, language: str, lines: dict[str, str]) -> str:
    if row.trigger_kind == TriggerKind.TIME.value and row.recurrence:
        return describe(RecurrenceSpec.model_validate(row.recurrence), language)
    condition = (row.condition_config or {}).get("type") or lines["routines_condition_unknown"]
    return lines["routines_condition"].format(condition=condition)


async def read_routines(*, user_id: UUID, language: str) -> PortraitSourceSection:
    """Render every active routine of one account.

    Args:
        user_id: The account.
        language: The language the recurrence is described in.

    Returns:
        The section; never raises.
    """
    try:
        async with get_db_context() as db:
            rows = await _rows(db, user_id)
        if not rows:
            return empty_section(KEY, "empty")
        lines = portrait_lines()
        items = [
            lines["routines_item"].format(
                title=flat_item(row.title),
                schedule=flat_item(_schedule(row, language, lines)),
                instruction=flat_item(row.action_prompt),
            )
            for row in rows
        ]
        header = lines["routines_header"].format(shown=len(items), total=len(items))
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
    table="scheduled_actions",
    user_column="user_id",
    stamp_column="updated_at",
    semantic_columns=(
        "title",
        "action_prompt",
        "recurrence",
        "trigger_kind",
        "condition_config",
        "is_enabled",
        "status",
    ),
)

install_portrait_source(KEY, read_routines, FRESHNESS)

__all__ = ["FRESHNESS", "KEY", "read_routines"]
