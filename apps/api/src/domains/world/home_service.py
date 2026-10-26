"""Owner-scoped colour preferences; no memory or interest read is needed."""

import asyncio
from uuid import UUID

from sqlalchemy import select

from src.core.config import settings
from src.core.exceptions import AuthorizationError, ResourceConflictError
from src.domains.feature_switches.guard import require_capability_fresh
from src.domains.feature_switches.registry import PlatformCapability
from src.domains.users.models import User
from src.domains.users.repository import UserRepository
from src.domains.world.home import (
    HomePreferences,
    HomeUpdate,
    HomeView,
    project_home,
    read_home_preferences,
)
from src.infrastructure.database.session import get_db_context


def _project(user: User) -> HomeView:
    """Project this owner's saved home colours without rewriting unreadable data."""
    preferences, needs_reset = read_home_preferences(user.world_preferences)
    return HomeView(
        owner_id=str(user.id),
        preferences=preferences,
        needs_reset=needs_reset,
        decoration=project_home(preferences, user.color_theme),
    )


async def read_owner_home(owner: UUID) -> HomeView:
    """Read active-owner home colours under fresh capability policy and a bounded timeout."""
    async with asyncio.timeout(settings.world_policy_timeout):
        async with get_db_context() as db:
            await require_capability_fresh(db, PlatformCapability.WORLD)
            user = await db.scalar(
                select(User).where(
                    User.id == owner,
                    User.is_active.is_(True),
                    User.deleted_at.is_(None),
                )
            )
            if user is None:
                raise AuthorizationError(detail={"error_code": "SESSION_UNAVAILABLE"})
            return _project(user)


async def update_owner_home(owner: UUID, request: HomeUpdate) -> HomeView:
    """Lock the active owner, reject stale revisions and atomically replace home preferences."""
    async with asyncio.timeout(settings.world_policy_timeout):
        async with get_db_context() as db:
            user = await UserRepository(db).get_by_id_for_preference_update(owner)
            if user is None:
                raise AuthorizationError(detail={"error_code": "SESSION_UNAVAILABLE"})
            await require_capability_fresh(db, PlatformCapability.WORLD)
            current, needs_reset = read_home_preferences(user.world_preferences)
            if request.expected_revision != current.revision:
                raise ResourceConflictError("world_home", detail={"error_code": "STALE_STATE"})
            if needs_reset and not request.reset:
                raise ResourceConflictError(
                    "world_home", detail={"error_code": "HOME_RESET_REQUIRED"}
                )
            layout = HomePreferences() if request.reset else request
            preferences = HomePreferences(
                revision=current.revision + 1,
                palette=layout.palette,
            )
            # Full replacement is required for SQLAlchemy JSONB change tracking.
            user.world_preferences = preferences.model_dump(mode="json")
            await db.flush()
            return _project(user)
