"""The Redis mutation validates the owner and current authority atomically."""

import json
from datetime import UTC, datetime, timedelta
from importlib import import_module
from uuid import uuid4

import pytest

from src.core.exceptions import AuthorizationError, ResourceConflictError
from src.infrastructure.cache.redis import get_redis_session
from src.infrastructure.cache.session_store import SessionStore

pytestmark = pytest.mark.integration


@pytest.mark.parametrize(
    "intervention",
    ["none", "owner", "malformed", "index", "current", "stamp", "expired", "future", "new_session"],
)
async def test_exact_selection_is_atomic_and_excludes_sessions_created_after_approval(
    intervention: str,
) -> None:
    revoke = import_module("src.infrastructure.cache.session_revocation").revoke_selected_sessions
    redis = await get_redis_session()
    store = SessionStore(redis)
    owner, other_owner = uuid4(), uuid4()
    current = await store.create_session(str(owner))
    first = await store.create_session(str(owner))
    second = await store.create_session(str(owner))
    new = None
    deadline = datetime.now(UTC) + timedelta(minutes=5)
    try:
        assert current.step_up_at is not None
        if intervention == "owner":
            data = first.to_dict()
            data["user_id"] = str(other_owner)
            await redis.set(f"session:{first.session_id}", json.dumps(data), keepttl=True)
        elif intervention == "malformed":
            await redis.set(f"session:{second.session_id}", "[]", keepttl=True)
        elif intervention == "index":
            await redis.srem(f"user:{owner}:sessions", first.session_id)
        elif intervention == "current":
            await store.delete_session(current.session_id)
        elif intervention == "stamp":
            data = current.to_dict()
            data["step_up_at"] = None
            await redis.set(f"session:{current.session_id}", json.dumps(data), keepttl=True)
        elif intervention == "expired":
            deadline = datetime.now(UTC) - timedelta(seconds=1)
        elif intervention == "future":
            current.step_up_at = datetime.now(UTC) + timedelta(minutes=1)
            await redis.set(
                f"session:{current.session_id}", json.dumps(current.to_dict()), keepttl=True
            )
        elif intervention == "new_session":
            new = await store.create_session(str(owner))
        if intervention in {"owner", "malformed", "index", "current", "stamp", "expired", "future"}:
            with pytest.raises((AuthorizationError, ResourceConflictError)):
                await revoke(
                    store,
                    owner,
                    (first, second),
                    current=current,
                    require_fresh_step_up=True,
                    approved_until=deadline,
                )
            assert await redis.exists(f"session:{first.session_id}")
            assert await redis.exists(f"session:{second.session_id}")
        else:
            assert (
                await revoke(
                    store,
                    owner,
                    (first, second),
                    current=current,
                    require_fresh_step_up=True,
                    approved_until=deadline,
                )
                == 2
            )
            assert not await redis.exists(f"session:{first.session_id}")
            assert not await redis.exists(f"session:{second.session_id}")
            assert await redis.exists(f"session:{current.session_id}")
            assert (
                await revoke(
                    store,
                    owner,
                    (first, second),
                    current=current,
                    require_fresh_step_up=True,
                    approved_until=deadline,
                )
                == 0
            )
            if new is not None:
                assert await redis.exists(f"session:{new.session_id}")
                assert await redis.sismember(f"user:{owner}:sessions", new.session_id)
    finally:
        for item in (current, first, second, new):
            if item is not None:
                await redis.delete(f"session:{item.session_id}")
        await redis.delete(f"user:{owner}:sessions")


async def test_ui_display_id_revocation_does_not_delete_a_record_whose_owner_changed(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    redis = await get_redis_session()
    store = SessionStore(redis)
    owner, other_owner = uuid4(), uuid4()
    selected = await store.create_session(str(owner))

    async def observed_then_changed(*args, **kwargs):
        data = selected.to_dict()
        data["user_id"] = str(other_owner)
        await redis.set(f"session:{selected.session_id}", json.dumps(data), keepttl=True)
        return [selected]

    monkeypatch.setattr(store, "list_user_sessions", observed_then_changed)
    try:
        with pytest.raises(ResourceConflictError):
            await store.delete_session_by_display_id(str(owner), selected.display_id)
        data = json.loads(await redis.get(f"session:{selected.session_id}"))
        assert data["user_id"] == str(other_owner)
    finally:
        await redis.delete(f"session:{selected.session_id}", f"user:{owner}:sessions")


@pytest.mark.parametrize("current_state", ["valid", "revoked", "stale"])
async def test_ui_revoke_others_requires_current_live_fresh_session(current_state: str) -> None:
    redis = await get_redis_session()
    store = SessionStore(redis)
    owner = uuid4()
    current = await store.create_session(str(owner))
    other = await store.create_session(str(owner))
    try:
        if current_state == "revoked":
            await store.delete_session(current.session_id)
        elif current_state == "stale":
            data = current.to_dict()
            data["step_up_at"] = (datetime.now(UTC) - timedelta(days=1)).isoformat()
            await redis.set(f"session:{current.session_id}", json.dumps(data), keepttl=True)
        if current_state == "valid":
            assert await store.delete_other_user_sessions(str(owner), current.session_id) == 1
            assert await redis.exists(f"session:{current.session_id}")
            assert not await redis.exists(f"session:{other.session_id}")
        else:
            with pytest.raises(AuthorizationError):
                await store.delete_other_user_sessions(str(owner), current.session_id)
            assert await redis.exists(f"session:{other.session_id}")
    finally:
        await redis.delete(
            f"session:{current.session_id}", f"session:{other.session_id}", f"user:{owner}:sessions"
        )


async def test_coarse_touch_keeps_step_up_and_ttl_and_does_not_resurrect_revoked_session() -> None:
    redis = await get_redis_session()
    store = SessionStore(redis)
    owner = uuid4()
    original = await store.create_session(str(owner))
    key = f"session:{original.session_id}"
    try:
        initial_ttl = await redis.ttl(key)
        await store.touch_last_seen(original.session_id)
        observed = await store.get_session(original.session_id)
        assert observed is not None and observed.last_seen_at is not None
        assert observed.step_up_at == original.step_up_at
        assert 0 < await redis.ttl(key) <= initial_ttl
        await store.touch_last_seen(original.session_id)
        second = await store.get_session(original.session_id)
        assert second is not None and second.last_seen_at == observed.last_seen_at
        await store.delete_session(original.session_id)
        await store.touch_last_seen(original.session_id)
        assert not await redis.exists(key)
    finally:
        await redis.delete(key, f"user:{owner}:sessions")
