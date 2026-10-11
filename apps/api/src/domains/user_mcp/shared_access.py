"""Fresh account/platform consent before shared MCP execution or cached-result access."""

from uuid import UUID

from sqlalchemy import select
from sqlalchemy.exc import SQLAlchemyError

from src.core.exceptions import AuthorizationError
from src.domains.feature_switches.guard import require_capability_fresh
from src.domains.feature_switches.registry import PlatformCapability
from src.domains.users.models import User
from src.infrastructure.database.session import get_db_context
from src.infrastructure.mcp.preferences_contract import saved_shared_mcp_refusals


async def require_shared_mcp_access(server_key: str, *, actor_id: UUID) -> None:
    try:
        async with get_db_context() as db:
            await require_capability_fresh(db, PlatformCapability.MCP)
            actor: User | None = await db.scalar(
                select(User)
                .where(User.id == actor_id, User.is_active, User.deleted_at.is_(None))
                .execution_options(populate_existing=True)
            )
            if actor is None or actor.id != actor_id or not actor.is_active or actor.is_deleted:
                raise AuthorizationError(detail={"error_code": "FORBIDDEN"})
            disabled = saved_shared_mcp_refusals(actor.admin_mcp_disabled_servers)
            if server_key in disabled:
                raise AuthorizationError(detail={"error_code": "MCP_SERVER_DISABLED"})
    except SQLAlchemyError, ValueError:
        raise AuthorizationError(detail={"error_code": "SERVICE_UNAVAILABLE"}) from None
