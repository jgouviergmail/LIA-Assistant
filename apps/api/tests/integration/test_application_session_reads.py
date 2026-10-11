"""Native and source UI session metadata share actual Redis and PostgreSQL owners."""

from uuid import uuid4

import pytest
from sqlalchemy import update
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.config import settings
from src.core.exceptions import AuthorizationError
from src.domains.agents.application.session_operations import read_session_settings
from src.domains.agents.application.session_schemas import DeviceSessionsRead
from src.domains.auth.session_queries import DeviceSessionsProjection
from src.domains.auth.sessions_router import list_sessions
from src.domains.notifications.models import UserFCMToken
from src.domains.users.models import User
from src.infrastructure.cache.redis import get_redis_session
from src.infrastructure.cache.session_store import SessionStore

pytestmark = pytest.mark.integration


async def test_account_deactivation_during_session_read_withholds_its_projection(
    async_session: AsyncSession, test_user: User, monkeypatch: pytest.MonkeyPatch
) -> None:
    from src.domains.agents.application import session_operations

    monkeypatch.setattr(settings, "application_tools_enabled", True)
    original_read = session_operations.read_device_sessions
    actor_id = test_user.id
    bind = async_session.bind
    assert bind is not None

    async def revoke_after_read(
        db: AsyncSession, user: User, store: SessionStore, *, cursor: str | None, limit: int
    ) -> DeviceSessionsProjection:
        result = await original_read(db, user, store, cursor=cursor, limit=limit)
        async with AsyncSession(bind=bind) as other_db:
            await other_db.execute(update(User).where(User.id == actor_id).values(is_active=False))
            await other_db.commit()
        return result

    monkeypatch.setattr(session_operations, "read_device_sessions", revoke_after_read)
    with pytest.raises(AuthorizationError):
        await read_session_settings(async_session, actor_id, DeviceSessionsRead())


async def test_session_pages_and_source_ui_omit_cookies_and_foreign_attestation_metadata(
    async_session: AsyncSession, test_user: User, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(settings, "application_tools_enabled", True)
    foreign_id = uuid4()
    foreign = User(
        id=foreign_id, email=f"foreign-session-{foreign_id}@example.test", is_active=True
    )
    async_session.add(foreign)
    await async_session.flush()
    token = UserFCMToken(
        id=uuid4(),
        user_id=test_user.id,
        token=f"private-delivery-{uuid4()}",
        device_type="web",
        device_name="My browser",
    )
    other_token = UserFCMToken(
        id=uuid4(),
        user_id=foreign.id,
        token=f"private-delivery-{uuid4()}",
        device_type="web",
        device_name="Foreign browser",
    )
    async_session.add_all([token, other_token])
    await async_session.commit()
    redis = await get_redis_session()
    store = SessionStore(redis)
    first = await store.create_session(
        str(test_user.id), auth_methods=["password"], fcm_token_id=str(token.id)
    )
    second = await store.create_session(str(test_user.id), fcm_token_id=str(other_token.id))
    other = await store.create_session(str(foreign.id))
    try:
        # A stale/corrupt index is not sufficient authority to serve a row.
        await redis.sadd(f"user:{test_user.id}:sessions", other.session_id)
        page = await read_session_settings(async_session, test_user.id, DeviceSessionsRead(limit=1))
        rest = await read_session_settings(
            async_session, test_user.id, DeviceSessionsRead(limit=1, cursor=page.next_cursor)
        )
        assert page.total == 2 and rest.next_cursor is None
        assert page.incomplete is True and rest.incomplete is True
        assert {row.id for row in page.sessions + rest.sessions} == {
            first.display_id,
            second.display_id,
        }
        assert page.current_session_known is False and all(
            row.current is None for row in page.sessions
        )
        rows = await list_sessions(
            user=test_user, db=async_session, store=store, lia_session=first.session_id
        )
        assert {row.id for row in rows} == {first.display_id, second.display_id}
        assert next(row for row in rows if row.id == first.display_id).current is True
        assert next(row for row in rows if row.id == first.display_id).device_name == "My browser"
        assert next(row for row in rows if row.id == second.display_id).device_name is None
        public = str(page.model_dump(mode="json")) + str(rest.model_dump(mode="json")) + str(rows)
        for secret in [
            first.session_id,
            second.session_id,
            other.session_id,
            str(token.id),
            str(other_token.id),
            token.token,
            other_token.token,
            "Foreign browser",
        ]:
            assert secret not in public
        with pytest.raises(ValueError):
            await read_session_settings(
                async_session, test_user.id, DeviceSessionsRead(cursor=other.display_id)
            )
    finally:
        for session in [first, second, other]:
            await store.delete_session(session.session_id)
        await redis.delete(f"user:{test_user.id}:sessions", f"user:{foreign.id}:sessions")
