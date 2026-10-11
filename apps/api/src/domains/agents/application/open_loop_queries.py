"""Explicit commitment reads retain both fresh capability guards and account authority."""

from datetime import UTC, datetime
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from src.core.constants import DEFAULT_USER_DISPLAY_TIMEZONE
from src.domains.agents.application.authorization import load_actor
from src.domains.agents.application.availability import require_application_tools
from src.domains.agents.application.open_loop_schemas import OpenLoopProjection, OpenLoopRead
from src.domains.feature_switches.guard import require_capability_fresh
from src.domains.feature_switches.registry import PlatformCapability
from src.domains.open_loops.management_read import read_open_loop_page


async def read_open_loops(
    db: AsyncSession, actor_id: UUID, query: OpenLoopRead
) -> OpenLoopProjection:
    selected = OpenLoopRead.model_validate(query.model_dump())
    await require_application_tools(db)
    await require_capability_fresh(db, PlatformCapability.OPEN_LOOPS)
    await load_actor(db, actor_id)
    page = await read_open_loop_page(
        db, actor_id, status=selected.status, limit=selected.limit, after_id=selected.after_id
    )
    await require_application_tools(db)
    await require_capability_fresh(db, PlatformCapability.OPEN_LOOPS)
    actor = await load_actor(db, actor_id)
    rows, more = page.rows[: selected.limit], len(page.rows) > selected.limit
    return OpenLoopProjection(
        items=rows,
        total=page.total,
        timezone=actor.timezone or DEFAULT_USER_DISPLAY_TIMEZONE,
        observed_at=datetime.now(UTC),
        returned_count=len(rows),
        truncated=more,
        next_cursor=rows[-1].id if more else None,
    )
