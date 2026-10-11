"""An older browser sample must never repopulate location after opt-out."""

from uuid import uuid4

import pytest
from sqlalchemy import delete
from sqlalchemy.ext.asyncio import AsyncEngine, async_sessionmaker

from src.core.security.utils import encrypt_data
from src.domains.auth.preference_commands import (
    AssistantPreferencePatch,
    update_assistant_preferences,
)
from src.domains.users.models import User
from src.domains.users.user_location_service import UserLocationService

pytestmark = pytest.mark.integration


async def test_sample_loaded_before_opt_out_cannot_restore_a_wiped_location(
    async_engine: AsyncEngine,
) -> None:
    sessions = async_sessionmaker(async_engine, expire_on_commit=False)
    actor = User(
        id=uuid4(),
        email=f"location-race-{uuid4()}@example.test",
        hashed_password="test-only",
        is_active=True,
        is_verified=True,
        use_last_known_location=True,
        last_known_location_encrypted=encrypt_data('{"lat": 48.8, "lon": 2.3}'),
    )
    try:
        async with sessions() as db:
            db.add(actor)
            await db.commit()
        async with sessions() as old_session, sessions() as control:
            stale = await old_session.get(User, actor.id)
            assert stale is not None and stale.use_last_known_location
            await old_session.commit()
            await update_assistant_preferences(
                control, actor.id, AssistantPreferencePatch(use_last_known_location=False)
            )
            outcome = await UserLocationService(old_session).update_last_known_location(
                stale,
                lat=48.8,
                lon=2.3,
                accuracy=10,
            )
            current = await control.get(User, actor.id, populate_existing=True)
            assert current is not None
            assert outcome.forbidden and not outcome.updated
            assert not current.use_last_known_location
            assert current.last_known_location_encrypted is None
            assert current.last_known_location_updated_at is None
    finally:
        async with sessions() as db:
            await db.execute(delete(User).where(User.id == actor.id))
            await db.commit()
