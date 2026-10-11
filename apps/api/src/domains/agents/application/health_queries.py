"""Fresh native/deployment authority never bypasses the source health-data consent."""

from datetime import UTC, datetime
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from src.core.config import settings
from src.core.constants import HEALTH_METRICS_USER_TOGGLE_ATTR
from src.core.exceptions import AuthorizationError
from src.domains.agents.application.authorization import load_actor
from src.domains.agents.application.availability import require_application_tools
from src.domains.agents.application.health_read_schemas import (
    HealthSamplesProjection,
    HealthSamplesRead,
    HealthTokensProjection,
    HealthTokensRead,
)
from src.domains.health_metrics import management_read


async def require_health_access(db: AsyncSession, actor_id: UUID, *, data: bool = True) -> None:
    await require_application_tools(db)
    actor = await load_actor(db, actor_id)
    if not settings.health_metrics_enabled or (
        data and not getattr(actor, HEALTH_METRICS_USER_TOGGLE_ATTR, False)
    ):
        raise AuthorizationError(detail={"error_code": "FORBIDDEN"})


async def read_health_samples(
    db: AsyncSession, actor_id: UUID, query: HealthSamplesRead
) -> HealthSamplesProjection:
    selected = HealthSamplesRead.model_validate(query.model_dump())
    await require_health_access(db, actor_id)
    now = datetime.now(UTC)
    as_of = selected.as_of or now
    if as_of > now:
        raise ValueError("Observation time cannot be in the future")
    page = await management_read.read_health_sample_page(
        db,
        actor_id,
        kind=selected.kind,
        from_ts=selected.from_ts,
        to_ts=selected.to_ts,
        limit=selected.limit,
        after_id=selected.after_id,
        as_of=as_of,
    )
    rows, more = page.rows[: selected.limit], len(page.rows) > selected.limit
    await require_health_access(db, actor_id)
    return HealthSamplesProjection(
        samples=rows,
        total=page.total,
        returned_count=len(rows),
        truncated=more,
        next_cursor=rows[-1].id if more else None,
        as_of=as_of,
        observed_at=datetime.now(UTC),
    )


async def read_health_tokens(
    db: AsyncSession, actor_id: UUID, query: HealthTokensRead | None = None
) -> HealthTokensProjection:
    selected = (
        HealthTokensRead() if query is None else HealthTokensRead.model_validate(query.model_dump())
    )
    await require_health_access(db, actor_id, data=False)
    now = datetime.now(UTC)
    as_of = selected.as_of or now
    if as_of > now:
        raise ValueError("Observation time cannot be in the future")
    page = await management_read.read_health_token_page(
        db, actor_id, limit=selected.limit, after_id=selected.after_id, as_of=as_of
    )
    rows, more = page.rows[: selected.limit], len(page.rows) > selected.limit
    await require_health_access(db, actor_id, data=False)
    return HealthTokensProjection(
        tokens=rows,
        total=page.total,
        returned_count=len(rows),
        truncated=more,
        next_cursor=rows[-1].id if more else None,
        as_of=as_of,
        observed_at=datetime.now(UTC),
    )
