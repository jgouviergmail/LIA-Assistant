"""The workboard as a portrait source: the tickets the person owns or holds (2026-10-12).

Installed into ``domains/shared/portrait_sources`` so ``journals`` reads it
without importing this domain. Two gates read at call time: the deployment
ceiling and the operator switch. Every ticket on the person's board (owned or
held, the board's own predicate) is rendered whole, nearest due date first,
with its status, priority, holder and description; a read that fails is
``unavailable``.
"""

from __future__ import annotations

from typing import Any
from uuid import UUID

import structlog
from sqlalchemy import select

from src.core.config import settings
from src.domains.feature_switches.registry import PlatformCapability, is_capability_enabled
from src.domains.shared.portrait_sources import (
    FreshnessProbe,
    PortraitSourceSection,
    empty_section,
    flat_item,
    install_portrait_source,
    portrait_lines,
)
from src.domains.workboard.board_queries import visible_predicate
from src.domains.workboard.constants import AssigneeKind
from src.domains.workboard.models import WorkboardTicket
from src.infrastructure.database.session import get_db_context

logger = structlog.get_logger(__name__)

KEY = "workboard"


async def _allowed(user_id: UUID | None = None) -> bool:
    return bool(settings.workboard_enabled) and await is_capability_enabled(
        PlatformCapability.WORKBOARD
    )


async def _rows(db: Any, user_id: UUID) -> list[WorkboardTicket]:
    """The person's whole board, nearest due date first (NULLs last), then creation, then id."""
    stmt = (
        select(WorkboardTicket)
        .where(visible_predicate(user_id))
        .order_by(
            WorkboardTicket.due_at.asc().nulls_last(),
            WorkboardTicket.created_at.asc(),
            WorkboardTicket.id,
        )
    )
    return list((await db.execute(stmt)).scalars().all())


def _item(row: WorkboardTicket, lines: dict[str, str]) -> str:
    return lines["workboard_item"].format(
        title=flat_item(row.title),
        status=row.status,
        priority=row.priority,
        due=lines["workboard_due"].format(date=f"{row.due_at:%Y-%m-%d}") if row.due_at else "",
        holder=lines["workboard_holder_lia"] if row.assignee_kind == AssigneeKind.LIA.value else "",
        description=f": {flat_item(row.description)}" if row.description else "",
    )


async def read_workboard(*, user_id: UUID, language: str) -> PortraitSourceSection:
    """Render every ticket on one account's board.

    Args:
        user_id: The account.
        language: Unused — a ticket is written in the person's own words.

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
        header = lines["workboard_header"].format(shown=len(items), total=len(items))
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


#: A ticket the person HOLDS but does not own lives under ``assignee_user_id``:
#: the board's predicate reads both columns, so the freshness probe does too.
FRESHNESS = FreshnessProbe(
    table="workboard_tickets",
    user_column="owner_user_id",
    stamp_column="updated_at",
    allowed=_allowed,
    semantic_columns=(
        "title",
        "description",
        "status",
        "priority",
        "due_at",
        "assignee_kind",
        "assignee_user_id",
    ),
    related_probes=(
        FreshnessProbe(
            table="workboard_tickets",
            user_column="assignee_user_id",
            stamp_column="updated_at",
            semantic_columns=("title", "description", "status", "priority", "due_at"),
        ),
    ),
)

install_portrait_source(KEY, read_workboard, FRESHNESS)

__all__ = ["FRESHNESS", "KEY", "read_workboard"]
