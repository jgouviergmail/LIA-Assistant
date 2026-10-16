"""Fresh authority and lifecycle checks shared by evidence collection and influence."""

from __future__ import annotations

from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.config import settings
from src.core.exceptions import AuthorizationError
from src.domains.feature_switches.guard import require_capability_fresh
from src.domains.feature_switches.registry import PlatformCapability
from src.domains.users.models import User


async def efficacy_enabled(db: AsyncSession, user_id: UUID, *, influence: bool = False) -> bool:
    if not settings.psyche_enabled:
        return False
    flag = (
        settings.psyche_efficacy_influence_enabled
        if influence
        else settings.psyche_efficacy_collection_enabled
    )
    if not flag:
        return False
    try:
        await require_capability_fresh(db, PlatformCapability.PSYCHE)
    except AuthorizationError:
        return False
    return bool(
        await db.scalar(
            select(User.psyche_enabled).where(
                User.id == user_id, User.is_active.is_(True), User.deleted_at.is_(None)
            )
        )
    )
