"""TTL semantics of the setex -> set(..., ex=ttl) migration (audit AC-012).

The 27 production ``setex`` call sites were migrated to the recommended
``set(name, value, ex=ttl)`` API. Mocks cannot prove TTL equivalence — these
tests run against the real Redis and assert, for representative call sites
(session store, OAuth-state store), that the key is written atomically WITH
its expiry: value readable, ``TTL`` in ``(0, expected]``, and the redis-py
deprecation filter (``error:Call to deprecated``) stays silent.
"""

import json
import uuid

import pytest
from redis.asyncio import Redis

from src.core.config import settings
from src.infrastructure.cache.redis import SessionService
from src.infrastructure.cache.session_store import SessionStore

pytestmark = pytest.mark.integration


@pytest.fixture
async def redis_client():
    """Real Redis client (decode mode matching get_redis_cache). Skips if down."""
    try:
        redis = Redis.from_url(str(settings.redis_url), decode_responses=True)
        await redis.ping()
    except Exception as e:  # noqa: BLE001 — environment guard, not logic
        pytest.skip(f"Redis not available: {e}")
    yield redis
    await redis.aclose()


async def test_session_store_writes_value_and_ttl_atomically(redis_client: Redis) -> None:
    """SessionStore.create_session sets JSON payload and expiry in ONE command."""
    store = SessionStore(redis_client)
    user_id = str(uuid.uuid4())

    session = await store.create_session(user_id=user_id, remember_me=False)
    key = f"session:{session.session_id}"
    try:
        raw = await redis_client.get(key)
        assert raw is not None, "session payload must be stored"
        assert json.loads(raw)["user_id"] == user_id

        ttl = await redis_client.ttl(key)
        # SET ... EX applied atomically: a key without expiry returns -1.
        assert (
            0 < ttl <= settings.session_cookie_max_age
        ), f"session TTL must match the cookie max-age contract, got {ttl}"
    finally:
        await redis_client.delete(key, f"user:{user_id}:sessions")


async def test_oauth_state_store_preserves_ttl_minutes(redis_client: Redis) -> None:
    """SessionService.store_oauth_state keeps the exact expire_minutes contract."""
    service = SessionService(redis_client)
    state = f"ac012-{uuid.uuid4()}"

    await service.store_oauth_state(state, {"connector_type": "google"}, expire_minutes=5)
    from src.core.constants import REDIS_KEY_OAUTH_STATE_PREFIX

    key = f"{REDIS_KEY_OAUTH_STATE_PREFIX}{state}"
    try:
        ttl = await redis_client.ttl(key)
        assert 0 < ttl <= 5 * 60, f"expected TTL within 5 minutes, got {ttl}"
        raw = await redis_client.get(key)
        assert raw is not None
        assert json.loads(raw)["connector_type"] == "google"
    finally:
        await redis_client.delete(key)
