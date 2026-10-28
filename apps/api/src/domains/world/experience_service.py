"""Revision-fenced owner presentation choices, with no assistant memory or LLM use."""

import asyncio
from uuid import UUID

from sqlalchemy import select

from src.core.config import settings
from src.core.exceptions import AuthorizationError, ResourceConflictError
from src.domains.feature_switches.guard import require_capability_fresh
from src.domains.feature_switches.registry import PlatformCapability
from src.domains.users.models import User
from src.domains.users.repository import UserRepository
from src.domains.world.experience import (
    ExperienceLayout,
    ExperiencePreferences,
    ExperienceUpdate,
    ExperienceView,
    read_experience_preferences,
)
from src.infrastructure.database.session import get_db_context


def _project(user: User) -> ExperienceView:
    """Project only this owner's supported preferences; preserve unreadable storage."""
    preferences, needs_reset = read_experience_preferences(user.world_experience_preferences)
    return ExperienceView(owner_id=str(user.id), preferences=preferences, needs_reset=needs_reset)


async def read_owner_experience(owner: UUID) -> ExperienceView:
    """Read the active owner's preferences under fresh World policy and a bounded timeout.

    Args:
        owner: The authenticated owner.

    Returns:
        The owner's supported preferences and whether storage needs the repair.

    Raises:
        AuthorizationError: World is off, or the owner is no longer active.
        TimeoutError: The policy deadline expired.
    """
    async with asyncio.timeout(settings.world_policy_timeout):
        async with get_db_context() as db:
            await require_capability_fresh(db, PlatformCapability.WORLD)
            user = await db.scalar(
                select(User).where(
                    User.id == owner, User.is_active.is_(True), User.deleted_at.is_(None)
                )
            )
            if user is None:
                raise AuthorizationError(detail={"error_code": "SESSION_UNAVAILABLE"})
            return _project(user)


async def update_owner_experience(owner: UUID, request: ExperienceUpdate) -> ExperienceView:
    """Lock the active owner and merge only explicitly edited fields into a new JSON document.

    Args:
        owner: The authenticated owner.
        request: The edited fields and observed revision, or an explicit repair.

    Returns:
        The saved preferences under their incremented revision.

    Raises:
        AuthorizationError: World is off, or the owner is no longer active.
        ResourceConflictError: The observed revision is stale, or unsupported
            storage needs the explicit repair first.
        TimeoutError: The policy deadline expired.
    """
    async with asyncio.timeout(settings.world_policy_timeout):
        async with get_db_context() as db:
            user = await UserRepository(db).get_by_id_for_preference_update(owner)
            if user is None:
                raise AuthorizationError(detail={"error_code": "SESSION_UNAVAILABLE"})
            await require_capability_fresh(db, PlatformCapability.WORLD)
            current, needs_reset = read_experience_preferences(user.world_experience_preferences)
            if request.expected_revision != current.revision:
                raise ResourceConflictError(
                    "world_experience", detail={"error_code": "STALE_STATE"}
                )
            if needs_reset and not request.reset:
                raise ResourceConflictError(
                    "world_experience", detail={"error_code": "EXPERIENCE_RESET_REQUIRED"}
                )
            layout = ExperiencePreferences() if request.reset else current
            values = layout.model_dump()
            if not request.reset:
                fields = request.model_fields_set & (
                    set(ExperienceLayout.model_fields) - {"version"}
                )
                values.update(request.model_dump(include=fields))
            values["revision"] = current.revision + 1
            preferences = ExperiencePreferences.model_validate(values)
            user.world_experience_preferences = preferences.model_dump(mode="json")
            await db.flush()
            return _project(user)
