"""Interest management uses source weight policy and never invokes discovery or paid work."""

from datetime import UTC, datetime
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from src.core.constants import DEFAULT_USER_DISPLAY_TIMEZONE
from src.core.exceptions import ResourceNotFoundError
from src.domains.agents.application.authorization import load_actor
from src.domains.agents.application.availability import require_application_tools
from src.domains.agents.application.interest_read_schemas import InterestProjection, InterestRead
from src.domains.interests.management_queries import read_interest_management_page
from src.domains.interests.models import InterestCategory, InterestStatus
from src.domains.interests.read_models import interest_to_response, user_to_settings_response
from src.domains.interests.repository import InterestRepository


async def read_interests(
    db: AsyncSession, actor_id: UUID, request: InterestRead
) -> InterestProjection:
    selected = InterestRead.model_validate(request.model_dump())
    await require_application_tools(db)
    await load_actor(db, actor_id)
    page = await read_interest_management_page(
        db,
        actor_id,
        limit=selected.limit,
        category=selected.category.value if selected.category else None,
        status=selected.status.value if selected.status else None,
        interest_id=selected.interest_id,
        after_id=selected.after_id,
    )
    await require_application_tools(db)
    actor = await load_actor(db, actor_id)
    if selected.interest_id is not None and not page.rows:
        raise ResourceNotFoundError("interest", str(selected.interest_id))
    rows, more = page.rows[: selected.limit], len(page.rows) > selected.limit
    now, repo = datetime.now(UTC), InterestRepository(db)
    return InterestProjection(
        interests=[interest_to_response(row, repo, now=now) for row in rows],
        total=sum(page.by_status.values()),
        active_count=page.by_status.get(InterestStatus.ACTIVE.value, 0),
        blocked_count=page.by_status.get(InterestStatus.BLOCKED.value, 0),
        dormant_count=page.by_status.get(InterestStatus.DORMANT.value, 0),
        settings=user_to_settings_response(actor),
        timezone=actor.timezone or DEFAULT_USER_DISPLAY_TIMEZONE,
        observed_at=now,
        returned_count=len(rows),
        total_available=page.matching_count,
        by_category={InterestCategory(key): value for key, value in page.by_category.items()},
        truncated=more,
        next_cursor=rows[-1].id if more else None,
    )
