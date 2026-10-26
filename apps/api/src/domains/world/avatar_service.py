"""Owner-scoped appearance persistence with the native fresh-row preference lock."""

import asyncio
from uuid import UUID

from sqlalchemy import select

from src.core.config import settings
from src.core.exceptions import AuthorizationError, ResourceConflictError
from src.domains.feature_switches.guard import require_capability_fresh
from src.domains.feature_switches.registry import PlatformCapability
from src.domains.users.models import User
from src.domains.users.repository import UserRepository
from src.domains.world.avatar import (
    AvatarPreferences,
    AvatarUpdate,
    AvatarView,
    public_world_name,
    read_avatar_preferences,
)
from src.infrastructure.database.session import get_db_context


def _project(user: User) -> AvatarView:
    """Project this owner's saved avatar preferences without rewriting unreadable data."""
    preferences, needs_reset = read_avatar_preferences(user.world_avatar_preferences)
    return AvatarView(
        owner_id=str(user.id),
        public_name=public_world_name(user.full_name, user.language),
        preferences=preferences,
        needs_setup=preferences.revision == 0 or needs_reset,
        needs_reset=needs_reset,
    )


async def read_owner_avatar(owner: UUID) -> AvatarView:
    """Read active-owner appearance under fresh capability policy and a bounded timeout."""
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


async def update_owner_avatar(owner: UUID, request: AvatarUpdate) -> AvatarView:
    """Lock the active owner, reject stale revisions and atomically replace avatar preferences."""
    async with asyncio.timeout(settings.world_policy_timeout):
        async with get_db_context() as db:
            user = await UserRepository(db).get_by_id_for_preference_update(owner)
            if user is None:
                raise AuthorizationError(detail={"error_code": "SESSION_UNAVAILABLE"})
            await require_capability_fresh(db, PlatformCapability.WORLD)
            current, needs_reset = read_avatar_preferences(user.world_avatar_preferences)
            if request.expected_revision != current.revision:
                raise ResourceConflictError("world_avatar", detail={"error_code": "STALE_STATE"})
            if needs_reset and not request.reset:
                raise ResourceConflictError(
                    "world_avatar", detail={"error_code": "AVATAR_RESET_REQUIRED"}
                )
            preferences = AvatarPreferences(
                revision=current.revision + 1,
                appearance=request.appearance,
            )
            # Replace only this JSONB column; home colors and native profile stay intact.
            user.world_avatar_preferences = preferences.model_dump(mode="json")
            await db.flush()
            return _project(user)
