"""Real Redis proves that origin authority expires and metadata never revives sessions."""

import json
from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy import update
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.config import settings
from src.core.exceptions import AuthorizationError
from src.domains.agents.application.security_operations import read_security_settings
from src.domains.agents.application.security_schemas import SecurityRead
from src.domains.agents.application.session_operations import read_session_settings
from src.domains.agents.application.session_schemas import DeviceSessionsRead
from src.domains.users.models import User
from src.infrastructure.application_sessions import bind_browser_session
from src.infrastructure.cache.redis import get_redis_session
from src.infrastructure.cache.session_store import SessionStore, UserSession

pytestmark = pytest.mark.integration


async def test_actual_origin_rechecks_step_up_and_revocation(test_user: User) -> None:
    redis = await get_redis_session()
    store = SessionStore(redis)
    session = await store.create_session(str(test_user.id))
    origin = bind_browser_session(test_user.id, session.session_id)
    assert origin is not None
    try:
        facts = await origin.require_session(
            test_user.id, expected_binding=origin.binding_id, recent_step_up=True
        )
        assert facts.display_id == session.display_id
        await store.delete_session(session.session_id)
        with pytest.raises(AuthorizationError):
            await origin.require_session(test_user.id, expected_binding=origin.binding_id)
    finally:
        await store.delete_session(session.session_id)


@pytest.mark.parametrize("write", ["step_up", "last_seen"])
async def test_metadata_update_never_recreates_a_revoked_or_expired_session(
    test_user: User, monkeypatch: pytest.MonkeyPatch, write: str
) -> None:
    redis = await get_redis_session()
    store = SessionStore(redis)
    session = await store.create_session(str(test_user.id))
    key = f"session:{session.session_id}"
    original = store.get_session

    async def disappear_after_read(session_id: str) -> UserSession | None:
        observed = await original(session_id)
        if observed is not None:
            observed.last_seen_at = None
        await redis.delete(key)
        return observed

    monkeypatch.setattr(store, "get_session", disappear_after_read)
    try:
        if write == "step_up":
            assert await store.mark_step_up(session.session_id) is False
        else:
            await store.touch_last_seen(session.session_id)
        assert await redis.exists(key) == 0 and await redis.ttl(key) == -2
    finally:
        await redis.delete(key)
        await redis.srem(f"user:{test_user.id}:sessions", session.session_id)


async def test_atomic_metadata_write_preserves_other_fields_and_fixed_ttl(test_user: User) -> None:
    redis = await get_redis_session()
    store = SessionStore(redis)
    session = await store.create_session(str(test_user.id))
    key = f"session:{session.session_id}"
    try:
        session.last_seen_at = None
        session.step_up_at = datetime.now(UTC) - timedelta(minutes=1)
        await redis.set(key, json.dumps(session.to_dict()), ex=60)
        await store.touch_last_seen(session.session_id)
        assert await store.mark_step_up(session.session_id)
        saved = await store.get_session(session.session_id)
        assert (
            saved is not None
            and saved.last_seen_at is not None
            and saved.step_up_at > session.step_up_at
        )
        assert 0 < await redis.ttl(key) <= 60
    finally:
        await store.delete_session(session.session_id)


async def test_activity_write_cannot_erase_a_concurrent_reauthentication(
    test_user: User, monkeypatch: pytest.MonkeyPatch
) -> None:
    redis = await get_redis_session()
    store, other = SessionStore(redis), SessionStore(redis)
    session = await store.create_session(str(test_user.id))
    original = store.get_session

    async def reauthenticate_after_read(session_id: str) -> UserSession | None:
        observed = await original(session_id)
        assert observed is not None
        observed.last_seen_at = None
        assert await other.mark_step_up(session_id)
        return observed

    monkeypatch.setattr(store, "get_session", reauthenticate_after_read)
    try:
        await store.touch_last_seen(session.session_id)
        fresh = await other.get_session(session.session_id)
        assert fresh is not None and fresh.step_up_at is not None and fresh.last_seen_at is not None
        assert fresh.step_up_at >= session.created_at
    finally:
        await other.delete_session(session.session_id)


async def test_native_current_session_and_freshness_come_from_the_transport(
    async_session: AsyncSession, test_user: User, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(settings, "application_tools_enabled", True)
    store = SessionStore(await get_redis_session())
    first = await store.create_session(str(test_user.id))
    second = await store.create_session(str(test_user.id))
    origin = bind_browser_session(test_user.id, first.session_id)
    assert origin is not None
    try:
        page = await read_session_settings(
            async_session, test_user.id, DeviceSessionsRead(), origin=origin
        )
        assert page.current_session_known is True
        assert {item.id for item in page.sessions if item.current} == {first.display_id}
        security = await read_security_settings(
            async_session, test_user.id, SecurityRead(), origin=origin
        )
        assert security.step_up_freshness == "fresh" and security.step_up_valid_until is not None
        await store.delete_session(first.session_id)
        with pytest.raises(AuthorizationError):
            await read_session_settings(
                async_session, test_user.id, DeviceSessionsRead(), origin=origin
            )
    finally:
        await store.delete_session(first.session_id)
        await store.delete_session(second.session_id)


@pytest.mark.parametrize("target", ["sessions", "security"])
@pytest.mark.parametrize("fault", ["operator", "actor"])
async def test_authority_is_rechecked_after_the_last_origin_read(
    async_session: AsyncSession,
    test_user: User,
    monkeypatch: pytest.MonkeyPatch,
    target: str,
    fault: str,
) -> None:
    from src.core.application_origin import ApplicationOrigin, ApplicationSessionFacts

    monkeypatch.setattr(settings, "application_tools_enabled", True)
    store = SessionStore(await get_redis_session())
    session = await store.create_session(str(test_user.id))
    original = bind_browser_session(test_user.id, session.session_id)
    assert original is not None
    actor_id = test_user.id

    async def revoke_after_proof() -> ApplicationSessionFacts | None:
        facts = await original.read_current()
        if fault == "operator":
            monkeypatch.setattr(settings, "application_tools_enabled", False)
        else:
            async with AsyncSession(bind=async_session.bind) as other:
                await other.execute(update(User).where(User.id == actor_id).values(is_active=False))
                await other.commit()
        return facts

    origin = ApplicationOrigin(
        user_id=actor_id, binding_id=original.binding_id, read_current=revoke_after_proof
    )
    try:
        with pytest.raises(AuthorizationError):
            if target == "sessions":
                await read_session_settings(
                    async_session, actor_id, DeviceSessionsRead(), origin=origin
                )
            else:
                await read_security_settings(async_session, actor_id, SecurityRead(), origin=origin)
    finally:
        await store.delete_session(session.session_id)
