"""Fresh account authority precedes security metadata queries and returned data."""

from datetime import UTC, datetime
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from src.core.application_origin import ApplicationOrigin
from src.core.config import settings
from src.core.session_freshness import step_up_valid_until
from src.domains.agents.application.authorization import load_actor
from src.domains.agents.application.availability import require_application_tools
from src.domains.agents.application.security_schemas import SecurityRead
from src.domains.auth.security_queries import AccountSecurityProjection, read_account_security


async def read_security_settings(
    db: AsyncSession,
    actor_id: UUID,
    request: SecurityRead,
    *,
    origin: ApplicationOrigin | None = None,
) -> AccountSecurityProjection:
    await require_application_tools(db)
    actor = await load_actor(db, actor_id)
    result = await read_account_security(
        db, actor, section=request.section, cursor=request.cursor, limit=request.limit
    )
    if origin is not None:
        facts = await origin.require_session(actor_id, expected_binding=origin.binding_id)
        horizon = step_up_valid_until(
            facts.step_up_at, datetime.now(UTC), settings.step_up_window_seconds
        )
        result = result.model_copy(
            update={
                "step_up_freshness": "fresh" if horizon is not None else "stale",
                "step_up_valid_until": horizon,
            }
        )
    await require_application_tools(db)
    await load_actor(db, actor_id)
    return result
