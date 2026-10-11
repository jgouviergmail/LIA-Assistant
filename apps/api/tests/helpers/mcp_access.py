"""Install the real MCP permission policy with an active owned SQL-row double."""

from collections.abc import Iterator
from contextlib import asynccontextmanager, contextmanager
from unittest.mock import AsyncMock, patch
from uuid import UUID, uuid4

from sqlalchemy.ext.asyncio import AsyncSession

from src.core.config import settings
from src.domains.user_mcp.shared_access import require_shared_mcp_access
from src.domains.users.models import User
from src.infrastructure.mcp.access_policy import configure_shared_mcp_access


@contextmanager
def installed_shared_mcp_access(actor_id: UUID | None = None) -> Iterator[User]:
    actor = User(
        id=actor_id or uuid4(), is_active=True, deleted_at=None, admin_mcp_disabled_servers=[]
    )
    db = AsyncMock(spec=AsyncSession)
    db.scalar.side_effect = [None, actor] * 16

    @asynccontextmanager
    async def session():
        yield db

    previous = configure_shared_mcp_access(require_shared_mcp_access)
    try:
        with (
            patch.object(settings, "mcp_enabled", True),
            patch(
                "src.domains.user_mcp.shared_access.get_db_context",
                session,
            ),
        ):
            yield actor
    finally:
        configure_shared_mcp_access(previous)
