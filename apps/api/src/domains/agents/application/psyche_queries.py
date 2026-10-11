"""Fresh authenticated psyche observation does not initialize, reset or generate prose."""

from datetime import UTC, datetime, timedelta
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.domains.agents.application.authorization import load_actor
from src.domains.agents.application.availability import require_application_tools
from src.domains.agents.application.psyche_read_schemas import PsycheProjection, PsycheRead
from src.domains.feature_switches.guard import require_capability_fresh
from src.domains.feature_switches.registry import PlatformCapability
from src.domains.psyche.management_projection import project_psyche_state
from src.domains.psyche.management_read import read_psyche_history_page
from src.domains.psyche.models import PsycheState
from src.domains.psyche.schemas import PsycheSettingsResponse
from src.domains.users.models import User


async def require_psyche_access(db: AsyncSession, actor_id: UUID) -> User:
    await require_application_tools(db)
    await require_capability_fresh(db, PlatformCapability.PSYCHE)
    return await load_actor(db, actor_id)


def psyche_settings(actor: User) -> PsycheSettingsResponse:
    return PsycheSettingsResponse.model_validate(
        {name: getattr(actor, name) for name in PsycheSettingsResponse.model_fields}
    )


async def read_psyche(db: AsyncSession, actor_id: UUID, query: PsycheRead) -> PsycheProjection:
    selected = PsycheRead.model_validate(query.model_dump())
    actor = await require_psyche_access(db, actor_id)
    preferences = psyche_settings(actor)
    now = datetime.now(UTC)
    as_of = selected.as_of or now
    if as_of > now:
        raise ValueError("History observation cannot be in the future")
    cutoff = as_of - timedelta(hours=selected.hours) if selected.hours else None
    stored = await db.scalar(
        select(PsycheState)
        .where(PsycheState.user_id == actor_id)
        .execution_options(populate_existing=True)
    )
    state, expression = project_psyche_state(stored) if stored is not None else (None, None)
    page = await read_psyche_history_page(
        db,
        actor_id,
        limit=selected.limit,
        after_id=selected.after_id,
        snapshot_type=selected.snapshot_type,
        cutoff=cutoff,
        as_of=as_of,
    )
    rows, more = page.rows[: selected.limit], len(page.rows) > selected.limit
    refreshed = await require_psyche_access(db, actor_id)
    if psyche_settings(refreshed) != preferences:
        raise ValueError("Psyche preferences changed while reading; retry")
    return PsycheProjection.model_validate(
        {
            "settings": preferences.model_dump(mode="json"),
            "state": state.model_dump(mode="json") if state else None,
            "expression": expression.model_dump(mode="json") if expression else None,
            "history": [entry.model_dump(mode="json") for entry in rows],
            "total": page.total,
            "returned_count": len(rows),
            "truncated": more,
            "next_cursor": rows[-1].id if more else None,
            "as_of": as_of,
            "observed_at": datetime.now(UTC),
        }
    )
