"""Native sessions, real SQL accounts/blocks, fresh operator switches and revocation."""

from datetime import UTC, datetime
from uuid import UUID, uuid4

import pytest
from redis.asyncio import Redis
from sqlalchemy import delete
from sqlalchemy.ext.asyncio import AsyncEngine, async_sessionmaker

from src.core.config import settings
from src.core.exceptions import BaseAPIException
from src.domains.peers.models import PeerBlock
from src.domains.system_settings.models import SystemSetting, SystemSettingKey
from src.domains.users.models import User
from src.domains.world import policy as world_policy
from src.infrastructure.cache.session_store import SessionStore

pytestmark = pytest.mark.integration


async def test_native_policy_reads_pair_blocks_and_rejects_revoked_or_deleted_accounts(
    async_engine: AsyncEngine,
    redis_world: Redis,
    committed_user_ids: list[UUID],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(settings, "world_enabled", True)

    async def sessions() -> Redis:
        return redis_world

    monkeypatch.setattr(world_policy, "get_redis_session", sessions)
    factory = async_sessionmaker(async_engine, expire_on_commit=False)
    async with factory() as db:
        owner = User(email=f"world-{uuid4().hex}@example.invalid", is_active=True, language="fr")
        peer = User(email=f"world-{uuid4().hex}@example.invalid", is_active=True, language="zh-CN")
        inactive = User(email=f"world-{uuid4().hex}@example.invalid", is_active=False)
        db.add_all([owner, peer, inactive])
        await db.flush()
        committed_user_ids.extend([owner.id, peer.id, inactive.id])
        db.add(PeerBlock(blocker_id=peer.id, blocked_id=owner.id))
        await db.commit()
    store = SessionStore(redis_world)
    session = await store.create_session(str(owner.id))
    participants = {str(peer.id), str(inactive.id)}
    try:
        policy = await world_policy.read_policy(session.session_id, str(owner.id), participants)
        assert policy.language == "fr"
        assert policy.blocked == {str(peer.id)}  # Reverse-direction block is enforced too.
        assert policy.eligible == {str(owner.id), str(peer.id)}
        with pytest.raises(BaseAPIException):
            await world_policy.read_policy(session.session_id, str(peer.id), participants)

        async with factory() as db:
            row = await db.get(User, owner.id)
            assert row is not None
            row.deleted_at = datetime.now(UTC)
            await db.commit()
        with pytest.raises(BaseAPIException):
            await world_policy.read_policy(session.session_id, str(owner.id), participants)
        # Native authentication refuses a soft-deleted row. Revocation itself
        # remains owned by the existing session/account lifecycle.
        await store.delete_session(session.session_id)
        with pytest.raises(BaseAPIException):
            await world_policy.read_policy(session.session_id, str(owner.id), participants)
    finally:
        await store.delete_session(session.session_id)


async def test_operator_switch_is_read_fresh_without_waiting_for_a_cached_config(
    async_engine: AsyncEngine,
    redis_world: Redis,
    committed_user_ids: list[UUID],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(settings, "world_enabled", True)

    async def sessions() -> Redis:
        return redis_world

    monkeypatch.setattr(world_policy, "get_redis_session", sessions)
    factory = async_sessionmaker(async_engine, expire_on_commit=False)
    async with factory() as db:
        owner = User(email=f"world-{uuid4().hex}@example.invalid", is_active=True, language="en")
        db.add(owner)
        await db.flush()
        committed_user_ids.append(owner.id)
        switch = SystemSetting(key=SystemSettingKey.CAPABILITY_WORLD_ENABLED, value="false")
        db.add(switch)
        await db.commit()
    store = SessionStore(redis_world)
    session = await store.create_session(str(owner.id))
    try:
        with pytest.raises(BaseAPIException):
            await world_policy.read_policy(session.session_id, str(owner.id), set())
        async with factory() as db:
            row = await db.get(SystemSetting, switch.id)
            assert row is not None
            row.value = "true"
            await db.commit()
        policy = await world_policy.read_policy(session.session_id, str(owner.id), set())
        assert policy.eligible == {str(owner.id)}
        await store.delete_session(session.session_id)
        with pytest.raises(BaseAPIException):
            await world_policy.read_policy(session.session_id, str(owner.id), set())
    finally:
        await store.delete_session(session.session_id)
        async with factory() as db:
            await db.execute(delete(SystemSetting).where(SystemSetting.id == switch.id))
            await db.commit()
