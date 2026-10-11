"""Explicit audit history reading never changes delivery, feedback or learning state."""

from datetime import UTC, datetime
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from src.core.constants import DEFAULT_USER_DISPLAY_TIMEZONE
from src.domains.agents.application.authorization import load_actor
from src.domains.agents.application.availability import require_application_tools
from src.domains.agents.application.interest_history_schemas import (
    InterestHistoryProjection,
    InterestHistoryRead,
)
from src.domains.interests.management_history import read_interest_history_page


async def read_interest_history(
    db: AsyncSession, actor_id: UUID, request: InterestHistoryRead
) -> InterestHistoryProjection:
    selected = InterestHistoryRead.model_validate(request.model_dump())
    await require_application_tools(db)
    await load_actor(db, actor_id)
    page = await read_interest_history_page(
        db, actor_id, limit=selected.limit, after_id=selected.after_id
    )
    await require_application_tools(db)
    actor = await load_actor(db, actor_id)
    rows, more = page.rows[: selected.limit], len(page.rows) > selected.limit
    return InterestHistoryProjection(
        notifications=rows,
        total=page.total,
        timezone=actor.timezone or DEFAULT_USER_DISPLAY_TIMEZONE,
        observed_at=datetime.now(UTC),
        returned_count=len(rows),
        truncated=more,
        next_cursor=rows[-1].id if more else None,
    )
