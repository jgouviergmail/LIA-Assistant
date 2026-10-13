"""The open loops as a portrait source: whole, gated, never raising (2026-10-12).

Installed into ``domains/shared/portrait_sources`` so ``journals`` reads it
without importing this domain. Two gates read at call time: the deployment
ceiling and the operator switch. Every OPEN loop is rendered, earliest deadline
first, beside the exact total; a read that fails is ``unavailable`` — a blind
source is named, never read as empty.
"""

from __future__ import annotations

from typing import Any
from uuid import UUID

import structlog
from sqlalchemy import select

from src.core.config import settings
from src.domains.feature_switches.registry import PlatformCapability, is_capability_enabled
from src.domains.open_loops.models import OpenLoop, OpenLoopDirection, OpenLoopStatus
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

KEY = "open_loops"


async def _allowed(user_id: UUID | None = None) -> bool:
    return bool(settings.open_loops_enabled) and await is_capability_enabled(
        PlatformCapability.OPEN_LOOPS
    )


async def _rows(db: Any, user_id: UUID) -> list[OpenLoop]:
    """Every OPEN loop, earliest deadline first (NULLs last), then creation, then id."""
    stmt = (
        select(OpenLoop)
        .where(OpenLoop.user_id == user_id, OpenLoop.status == OpenLoopStatus.OPEN.value)
        .order_by(OpenLoop.due_hint.asc().nulls_last(), OpenLoop.created_at.asc(), OpenLoop.id)
    )
    return list((await db.execute(stmt)).scalars().all())


def _item(row: OpenLoop, lines: dict[str, str]) -> str:
    direction = (
        "open_loops_direction_owes"
        if row.direction == OpenLoopDirection.USER_OWES.value
        else "open_loops_direction_waiting"
    )
    return lines["open_loops_item"].format(
        subject=flat_item(row.subject),
        direction=lines[direction],
        counterparty=f", {flat_item(row.counterparty)}" if row.counterparty else "",
        due=lines["open_loops_due"].format(date=f"{row.due_hint:%Y-%m-%d}") if row.due_hint else "",
    )


async def read_open_loops(*, user_id: UUID, language: str) -> PortraitSourceSection:
    """Render every open loop of one account.

    Args:
        user_id: The account.
        language: Unused — a loop is stored as the person said it.

    Returns:
        The section; never raises.
    """
    try:
        if not await _allowed(user_id):
            return empty_section(KEY, "disabled")
        async with get_db_context() as db:
            rows = await _rows(db, user_id)
        if not rows:
            return empty_section(KEY, "empty")
        lines = portrait_lines()
        items = [_item(row, lines) for row in rows]
        header = lines["open_loops_header"].format(shown=len(items), total=len(items))
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
    table="open_loops",
    user_column="user_id",
    stamp_column="updated_at",
    allowed=_allowed,
    semantic_columns=("subject", "counterparty", "direction", "due_hint", "status"),
)

install_portrait_source(KEY, read_open_loops, FRESHNESS)

__all__ = ["FRESHNESS", "KEY", "read_open_loops"]
